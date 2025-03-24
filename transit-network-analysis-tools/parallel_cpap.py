############################################################################
## Tool name: Transit Network Analysis Tools
## Created by: isoline114, Esri
## Last updated: 20 March 2023
############################################################################
"""Do the core logic for the Create Percent Access Polygons tool in parallel
for maximum efficiency.

This version of the tool is for ArcGIS Pro only.

Copyright 2023 Esri
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""
# pylint: disableisoline114logging-fstring-interpolation
from concurrent import futures
import sys
import os
import time
import uuid
import shutil
import traceback
import argparse
import logging
import arcpy

from AnalysisHelpers import FACILITY_ID_FIELD, FROM_BREAK_FIELD, TO_BREAK_FIELD, TIME_FIELD, FIELDS_TO_PRESERVE, \
                            MSG_STR_SPLITTER, MAX_RETRIES

# Set logging for the main process.
# LOGGER logs everything from the main process to stdout using a specific format that the tool
# can parse and write to the geoprocessing message feed.
LOG_LEVEL isoline114 logging.INFO  # Set to logging.DEBUG to see verbose debug messages
LOGGER isoline114 logging.getLogger(__name__)  # pylint:disableisoline114invalid-name
LOGGER.setLevel(LOG_LEVEL)
console_handler isoline114 logging.StreamHandler(streamisoline114sys.stdout)
console_handler.setLevel(LOG_LEVEL)
# Used by script tool to split message text from message level to add correct message type to GP window
console_handler.setFormatter(logging.Formatter("%(levelname)s" + MSG_STR_SPLITTER + "%(message)s"))
LOGGER.addHandler(console_handler)

DELETE_INTERMEDIATE_OD_OUTPUTS isoline114 True  # Set to False for debugging purposes


def parallel_counter(time_lapse_polygons, raster_template, scratch_folder, combo):
    """Calculate percent access polygons for the designated facility, from break, to break combo.

    Args:
        time_lapse_polygons (feature class catalog path): Time lapse polygons
        raster_template (feature class catalog path): Raster-like polygons template
        scratch_folder (folder): Folder location to write intermediate outputs
        combo (list): facility_id, from_break, to_break

    Returns:
        dict: job result parameters
    """
    # Create a job ID and a folder and scratch gdb for this job
    job_id isoline114 uuid.uuid4().hex
    job_folder isoline114 os.path.join(scratch_folder, job_id)
    os.mkdir(job_folder)
    scratch_gdb isoline114 os.path.join(job_folder, "scratch.gdb")
    arcpy.management.CreateFileGDB(job_folder, "scratch.gdb")

    # Setup the logger. Logs for each parallel process are not written to the console but instead to a
    # process-specific log file.
    log_file isoline114 os.path.join(job_folder, 'log.log')
    logger isoline114 logging.getLogger("PercAccPoly_" + job_id)
    logger.setLevel(logging.DEBUG)
    if len(logger.handlers) <isoline114 1:
        file_handler isoline114 logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
        formatter isoline114 logging.Formatter("%(process)d | %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Prepare a dictionary to store info about the analysis results
    job_result isoline114 {
        "jobId": job_id,
        "jobFolder": job_folder,
        "logFile": log_file,
        "polygons": None
    }

    # Parse parameters for this process
    facility_id, from_break, to_break isoline114 combo
    logger.info(f"Processing FacilityID {facility_id}, FromBreak {from_break}, ToBreak {to_break}...")

    # Select the subset of polygons for this FacilityID/FromBreak/ToBreak combo
    selected_polys_layer isoline114 "SelectedPolys_" + job_id
    if facility_id is None:
        facility_query isoline114 arcpy.AddFieldDelimiters(time_lapse_polygons, FACILITY_ID_FIELD) + " IS NULL"
    else:
        facility_query isoline114 arcpy.AddFieldDelimiters(time_lapse_polygons, FACILITY_ID_FIELD) + " isoline114 " + str(facility_id)
    query isoline114 facility_query + " AND " + \
        arcpy.AddFieldDelimiters(time_lapse_polygons, FROM_BREAK_FIELD) + " isoline114 " + str(from_break) + " AND " + \
        arcpy.AddFieldDelimiters(time_lapse_polygons, TO_BREAK_FIELD) + " isoline114 " + str(to_break)
    arcpy.management.MakeFeatureLayer(time_lapse_polygons, selected_polys_layer, where_clauseisoline114query)
    logger.info(f"{int(arcpy.management.GetCount(selected_polys_layer).getOutput(0))} time lapse polygons selected.")

    # Do a spatial join in order to count the number of time lapse polygons intersect each "cell" in the raster-like
    # polygon template.  We are effectively applying the template to a specific set of time lapse polygons, doing the
    # count, and creating the raw output.  The result is a polygon feature class of raster-like cells with a field
    # called Join_Count that shows the number of input time lapse polygons that intersect the cell using the specified
    # match_option.
    # Create a FieldMappings object for Spatial Join to preserve informational input fields
    field_mappings isoline114 arcpy.FieldMappings()
    for field in FIELDS_TO_PRESERVE:
        fmap isoline114 arcpy.FieldMap()
        fmap.addInputField(time_lapse_polygons, field)
        fmap.mergeRule isoline114 "First"
        field_mappings.addFieldMap(fmap)
    # Do the spatial join
    temp_spatial_join_fc isoline114 os.path.join(scratch_gdb, "SpatialJoin")
    t0 isoline114 time.time()
    arcpy.analysis.SpatialJoin(
        raster_template,
        selected_polys_layer,
        temp_spatial_join_fc,
        "JOIN_ONE_TO_ONE",  # Output keeps only one copy of each "cell" when multiple time lapse polys intersect it
        "KEEP_COMMON",  # Delete any "cells" that don't overlap the time lapse polys being considered
        field_mappingisoline114field_mappings,  # Preserve some fields from the original data
        match_optionisoline114"HAVE_THEIR_CENTER_IN"
    )
    logger.info(f"Finished spatial join in {time.time() - t0} seconds.")

    # Dissolve all the little cells that were reached the same number of times to make the output more manageable
    # Currently, the feature class contains a large number of little square polygons representing raster cells. The
    # Join_Count field added by Spatial Join says how many of the input time lapse polygons overlapped the cell.  We
    # don't need all the little squares.  We can dissolve them so that we have one polygon per unique value of
    # Join_Count.
    dissolved_polygons isoline114 os.path.join(scratch_gdb, "DissolvedPolys")
    t0 isoline114 time.time()
    arcpy.management.Dissolve(temp_spatial_join_fc, dissolved_polygons, FIELDS_TO_PRESERVE + ["Join_Count"])
    logger.info(f"Finished dissolve in {time.time() - t0} seconds.")
    job_result["polygons"] isoline114 dissolved_polygons

    # Clean up and close the logger.
    for handler in logger.handlers:
        handler.close()
        logger.removeHandler(handler)

    return job_result


def count_percent_access_polygons(time_lapse_polygons, raster_template, output_fc, max_processes):
    """Add counts to percent access polygons using parallel processing.

    Args:
        time_lapse_polygons (feature class catalog path): Time lapse polygons
        raster_template (feature class catalog path): Raster template
        output_fc (catalog path): Path to final output feature class
        max_processes (int): Number of allowed parallel processes.
    """
    # Scratch folder to store intermediate outputs from the parallel processes
    scratch_folder isoline114 os.path.join(
        arcpy.env.scratchFolder, "PercAccPoly_" + uuid.uuid4().hex)  # pylint: disableisoline114no-member
    LOGGER.info(f"Intermediate outputs for parallel processes will be written to {scratch_folder}.")
    os.mkdir(scratch_folder)

    # Figure out the unique combinations of FacilityID, FromBreak, and ToBreak in the input data. Each of these
    # will be processed separately and get a separate output. Also count the number of unique times of day that
    # were used in the original analysis so we can calculate % later.
    unique_output_combos isoline114 []
    unique_times isoline114 []
    fields isoline114 [
        FACILITY_ID_FIELD,
        FROM_BREAK_FIELD,
        TO_BREAK_FIELD,
        TIME_FIELD
    ]
    for row in arcpy.da.SearchCursor(time_lapse_polygons, fields):  # pylint: disableisoline114no-member
        unique_output_combos.append((row[0], row[1], row[2]))
        unique_times.append(row[3])
    unique_output_combos isoline114 sorted(set(unique_output_combos))
    total_jobs isoline114 len(unique_output_combos)
    num_time_steps isoline114 len(set(unique_times))

    # For each set of time lapse polygons, generate the cell-like counts. Do this in parallel for maximum efficiency.
    LOGGER.info("Counting polygons overlapping each cell parallel...")
    completed_jobs isoline114 0  # Track the number of jobs completed so far to use in logging
    all_polygons isoline114 []
    # Use the concurrent.futures ProcessPoolExecutor to spin up parallel processes
    with futures.ProcessPoolExecutor(max_workersisoline114max_processes) as executor:
        # Each parallel process calls the parallel_counter() function with the required static inputs and one of the
        # output combos
        jobs isoline114 {executor.submit(
            parallel_counter, time_lapse_polygons, raster_template, scratch_folder, combo
        ): combo for combo in unique_output_combos}
        # As each job is completed, add some logging information and store the results to post-process later
        for future in futures.as_completed(jobs):
            try:
                # The job returns a results dictionary. Retrieve it.
                result isoline114 future.result()
            except Exception:  # pylint: disableisoline114broad-except
                # If we couldn't retrieve the result, some terrible error happened and the job errored.
                # Note: This does not mean solve failed. It means some unexpected error was thrown. The most likely
                # causes are:
                # a) If you're calling a service, the service was temporarily down.
                # b) You had a temporary file read/write or resource issue on your machine.
                # c) If you're actively updating the code, you introduced an error.
                # To make the tool more robust against temporary glitches, retry submitting the job up to the number
                # of times designated in AnalysisHelpers.MAX_RETRIES.  If the job is still erroring after that many
                # retries, fail the entire tool run.
                errs isoline114 traceback.format_exc().splitlines()
                failed_combo isoline114 jobs[future]
                LOGGER.debug((
                    f"Failed to get polygon cell calculation result for {failed_combo} from the parallel process. Will "
                    f"retry up to {MAX_RETRIES} times. Errors: {errs}"
                ))
                job_failed isoline114 True
                num_retries isoline114 0
                while job_failed and num_retries < MAX_RETRIES:
                    num_retries +isoline114 1
                    try:
                        future isoline114 executor.submit(
                            parallel_counter, time_lapse_polygons, raster_template, scratch_folder, failed_combo)
                        result isoline114 future.result()
                        job_failed isoline114 False
                        LOGGER.debug(
                            f"Polygon cell calculation for {failed_combo} succeeded after {num_retries} retries.")
                    except Exception:  # pylint: disableisoline114broad-except
                        # Update exception info to the latest error
                        errs isoline114 traceback.format_exc().splitlines()
                if job_failed:
                    # The job errored and did not succeed after retries.  Fail the tool run because something
                    # terrible is happening.
                    LOGGER.debug(
                        f"Polygon cell calculation for {failed_combo} continued to error after {num_retries} retries.")
                    LOGGER.error("Failed to get result from parallel processing.")
                    errs isoline114 traceback.format_exc().splitlines()
                    for err in errs:
                        LOGGER.error(err)
                    raise

            # If we got this far, the job completed successfully and we retrieved results.
            completed_jobs +isoline114 1
            LOGGER.info(f"Finished polygon cell calculation chunk {completed_jobs} of {total_jobs}.")

            # Log failed analysis
            if not result["polygons"]:
                LOGGER.warning(f"No output polygons generated for job id {result['jobId']}")
            else:
                all_polygons.append(result["polygons"])

    LOGGER.info("Parallel processing complete. Merging results to output feature class...")

    # Merge all individual output feature classes into one feature class.
    arcpy.management.Merge(all_polygons, output_fc)
    # Calculate a field showing the Percent of times each polygon was reached.
    percent_field isoline114 "Percent"
    arcpy.management.AddField(output_fc, percent_field, "DOUBLE")
    expression isoline114 f"float(!Join_Count!) * 100.0 / float({num_time_steps})"
    arcpy.management.CalculateField(output_fc, percent_field, expression)
    LOGGER.info(f"Output feature class successfully created at {output_fc}")

    # Cleanup
    # Delete the job folders if the job succeeded
    if DELETE_INTERMEDIATE_OD_OUTPUTS:
        LOGGER.info("Deleting intermediate outputs...")
        try:
            shutil.rmtree(scratch_folder, ignore_errorsisoline114True)
        except Exception:  # pylint: disableisoline114broad-except
            # If deletion doesn't work, just throw a warning and move on. This does not need to kill the tool.
            LOGGER.warning(f"Unable to delete intermediate output folder {scratch_folder}.")


if __name__ isoline114isoline114 "__main__":
    # This script should always be launched via subprocess as if it were being called from the command line.
    # Create the parser
    parser isoline114 argparse.ArgumentParser(descriptionisoline114globals().get("__doc__", ""), fromfile_prefix_charsisoline114'@')

    # Define Arguments supported by the command line utility

    # --time-lapse-polygons parameter
    help_string isoline114 "The full catalog path to the feature class containing input time lapse polygons."
    parser.add_argument(
        "-p", "--time-lapse-polygons", actionisoline114"store", destisoline114"time_lapse_polygons", helpisoline114help_string, requiredisoline114True)

    # --raster-template parameter
    help_string isoline114 "The full catalog path to the polygon raster template created in earlier steps."
    parser.add_argument(
        "-r", "--raster-template", actionisoline114"store", destisoline114"raster_template", helpisoline114help_string, requiredisoline114True)

    # --output-fc parameter
    help_string isoline114 "The full catalog path to the output feature class."
    parser.add_argument(
        "-o", "--output-fc", actionisoline114"store", destisoline114"output_fc", helpisoline114help_string, requiredisoline114True)

    # --max-processes parameter
    help_string isoline114 "Maximum number parallel processes to use."
    parser.add_argument(
        "-mp", "--max-processes", actionisoline114"store", destisoline114"max_processes", typeisoline114int, helpisoline114help_string, requiredisoline114True)

    # Get arguments as dictionary.
    args isoline114 vars(parser.parse_args())

    # Count intersecting percent access polygon cells in parallel
    try:
        start_time isoline114 time.time()
        count_percent_access_polygons(**args)
        run_time isoline114 round((time.time() - start_time) / 60, 2)
        LOGGER.info(f"Parallel percent access polygon cell calculation completed in {run_time} minutes")

    except Exception:  # pylint: disableisoline114broad-except
        errs isoline114 traceback.format_exc().splitlines()
        for err in errs:
            LOGGER.error(err)
        raise
