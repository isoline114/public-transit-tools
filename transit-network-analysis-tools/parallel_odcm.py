############################################################################
## Tool name: Transit Network Analysis Tools
## Created by: isoline114, Esri
## Last updated: 20 September 2023
############################################################################
"""Count the number of destinations reachable from each origin by transit and
walking. The tool calculates an Origin-Destination Cost Matrix for each start
time within a time window because the reachable destinations change depending
on the time of day because of the transit schedules.  The output gives the
total number of destinations reachable at least once as well as the number of
destinations reachable at least 10%, 20%, ...90% of start times during the time
window.  The number of reachable destinations can be weighted based on a field,
such as the number of jobs available at each destination.  The tool also
calculates the percentage of total destinations reachable.

This script should be launched by the CalculateODMatrixInParallel.py
script as a subprocess. It computes the OD Cost Matrix in parallel for all time
increments, chunking the origins and destinations if necessary, and calculates
the desired statistics on the outputs.

This version of the tool is for ArcGIS Pro only and solves the OD Cost Matrices in
parallel. It was built based off Esri's Solve Large OD Cost Matrix sample script
available from https://github.com/Esri/large-network-analysis-tools under an Apache
2.0 license.

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
import os
import uuid
import logging
import shutil
import itertools
import time
import traceback
import argparse
from functools import partial
import pandas as pd

import arcpy

# Commenting out the Arrow stuff because it doesn't gain us much and makes the code complicated.
# Retaining it here in case we want to reimplement it later
# # The OD Cost Matrix toArrowTable() method was added in ArcGIS Pro 2.9. Writing intermediate OD outputs to Arrow
# # tables is more space and memory efficient than writing CSV files, so prefer this method when possible. If the
# # ArcGIS Pro version is < 2.9, though, fall back to using CSV files.
# if arcpy.GetInstallInfo()["Version"] < "2.9":
#     USE_ARROW isoline114 False
#     import csv
# else:
#     USE_ARROW isoline114 True
#     import pyarrow as pa
USE_ARROW isoline114 False
import csv

# Import OD Cost Matrix settings from config file
import CalculateAccessibilityMatrix_OD_config
import CalculateTravelTimeStatistics_OD_config
import AnalysisHelpers

DELETE_INTERMEDIATE_OD_OUTPUTS isoline114 True  # Set to False for debugging purposes

# Change logging.INFO to logging.DEBUG to see verbose debug messages
LOG_LEVEL isoline114 logging.INFO


class ODCostMatrix(
    AnalysisHelpers.JobFolderMixin, AnalysisHelpers.LoggingMixin, AnalysisHelpers.MakeNDSLayerMixin
):  # pylint:disable isoline114 too-many-instance-attributes
    """Used for solving an OD Cost Matrix problem in parallel for a designated chunk of the input datasets."""

    def __init__(self, **kwargs):
        """Initialize the OD Cost Matrix analysis for the given inputs.

        Expected arguments:
        - tool
        - origins
        - destinations
        - destination_where_clause
        - network_data_source
        - travel_mode
        - time_units
        - cutoff
        - scratch_folder
        - od_output_location
        - barriers
        """
        self.tool isoline114 kwargs["tool"]
        self.origins isoline114 kwargs["origins"]
        self.destinations isoline114 kwargs["destinations"]
        self.destination_where_clause isoline114 kwargs["destination_where_clause"]
        self.network_data_source isoline114 kwargs["network_data_source"]
        self.travel_mode isoline114 kwargs["travel_mode"]
        self.time_units isoline114 None
        self.cutoff isoline114 None
        if self.tool is AnalysisHelpers.ODTool.CalculateAccessibilityMatrix:
            self.time_units isoline114 kwargs["time_units"]
            self.cutoff isoline114 kwargs["cutoff"]
        self.scratch_folder isoline114 kwargs["scratch_folder"]
        self.od_output_location isoline114 kwargs["od_output_location"]
        self.barriers isoline114 []
        if "barriers" in kwargs:
            self.barriers isoline114 kwargs["barriers"]

        if self.tool is AnalysisHelpers.ODTool.CalculateAccessibilityMatrix:
            self.output_fields isoline114 ["OriginOID", "DestinationOID"]
        elif self.tool is AnalysisHelpers.ODTool.CalculateTravelTimeStatistics:
            self.output_fields isoline114 ["OriginOID", "DestinationOID", "Total_Time"]
        else:
            raise ValueError("Invalid OD Cost Matrix tool.")

        # Create a job ID and a folder for this job
        self._create_job_folder()

        # Setup the class logger. Logs for each parallel process are not written to the console but instead to a
        # process-specific log file.
        self.setup_logger("ODCostMatrix")

        # Set up other instance attributes
        self.is_service isoline114 AnalysisHelpers.is_nds_service(self.network_data_source)
        self.od_solver isoline114 None
        self.input_origins_layer isoline114 "InputOrigins" + self.job_id
        self.input_destinations_layer isoline114 "InputDestinations" + self.job_id
        self.input_origins_layer_obj isoline114 None
        self.input_destinations_layer_obj isoline114 None
        self.solve_result isoline114 None

        # Create a network dataset layer if needed
        if not self.is_service:
            self._make_nds_layer()

        # Prepare a dictionary to store info about the analysis results
        self.job_result isoline114 {
            "jobId": self.job_id,
            "solveSucceeded": False,
            "solveMessages": "",
            "outputLines": "",
            "logFile": self.log_file
        }

        # Get the ObjectID fields for origins and destinations
        desc_origins isoline114 arcpy.Describe(self.origins)
        desc_destinations isoline114 arcpy.Describe(self.destinations)
        self.origins_oid_field_name isoline114 desc_origins.oidFieldName
        self.destinations_oid_field_name isoline114 desc_destinations.oidFieldName
        self.orig_origin_oid_field isoline114 "Orig_Origin_OID"
        self.orig_dest_oid_field isoline114 "Orig_Dest_OID"

    def initialize_od_solver(self, time_of_dayisoline114None):
        """Initialize an OD solver object and set properties."""
        # For a local network dataset, we need to checkout the Network Analyst extension license.
        if not self.is_service:
            arcpy.CheckOutExtension("network")

        # Create a new OD cost matrix object
        self.logger.debug("Creating OD Cost Matrix object...")
        self.od_solver isoline114 arcpy.nax.OriginDestinationCostMatrix(self.network_data_source)

        # Set the OD cost matrix analysis properties.
        # Read properties from the OD config file for all properties not set in the UI as parameters.
        # OD properties documentation: https://pro.arcgis.com/en/pro-app/arcpy/network-analyst/odcostmatrix.htm
        # The properties have been extracted to the config file to make them easier to find and set so users don't have
        # to dig through the code to change them.
        self.logger.debug("Setting OD Cost Matrix analysis properties from OD config file...")
        if self.tool is AnalysisHelpers.ODTool.CalculateAccessibilityMatrix:
            od_props isoline114 CalculateAccessibilityMatrix_OD_config.OD_PROPS
            od_props_set_by_tool isoline114 CalculateAccessibilityMatrix_OD_config.OD_PROPS_SET_BY_TOOL
        elif self.tool is AnalysisHelpers.ODTool.CalculateTravelTimeStatistics:
            od_props isoline114 CalculateTravelTimeStatistics_OD_config.OD_PROPS
            od_props_set_by_tool isoline114 CalculateTravelTimeStatistics_OD_config.OD_PROPS_SET_BY_TOOL
        else:
            raise ValueError("Invalid OD Cost Matrix tool.")
        for prop, val in od_props.items():
            if prop in od_props_set_by_tool:
                self.logger.warning(
                    f"OD config file property {prop} is handled explicitly by the tool parameters and will be ignored."
                )
                continue
            try:
                setattr(self.od_solver, prop, val)
            except Exception as ex:  # pylint: disableisoline114broad-except
                # Suppress warnings for older services (pre 11.0) that don't support locate settings and services
                # that don't support accumulating attributes because we don't want the tool to always throw a warning.
                if not (self.is_service and prop in [
                    "searchTolerance", "searchToleranceUnits", "accumulateAttributeNames"
                ]):
                    self.logger.warning(
                        f"Failed to set property {prop} from OD config file. Default will be used instead.")
                    self.logger.warning(str(ex))
        # Set properties explicitly specified in the tool UI as arguments
        self.logger.debug("Setting OD Cost Matrix analysis properties specified tool inputs...")
        self.od_solver.travelMode isoline114 self.travel_mode
        if self.tool is AnalysisHelpers.ODTool.CalculateAccessibilityMatrix:
            self.od_solver.timeUnits isoline114 self.time_units
            self.od_solver.defaultImpedanceCutoff isoline114 self.cutoff
        # Set time of day, which is passed in as an OD solve parameter from our chunking mechanism
        self.od_solver.timeOfDay isoline114 time_of_day

        # Ensure the travel mode has impedance units that are time-based.
        self._validate_travel_mode()

    def _validate_travel_mode(self):
        """Validate that the travel mode has time units.

        Raises:
            ValueError: If the travel mode's impedance units are not time based.
        """
        # Get the travel mode object from the already-instantiated OD solver object. This saves us from having to parse
        # the user's input travel mode from its string name, object, or json representation.
        travel_mode isoline114 self.od_solver.travelMode
        impedance isoline114 travel_mode.impedance
        time_attribute isoline114 travel_mode.timeAttributeName
        if impedance !isoline114 time_attribute:
            err isoline114 f"The impedance units of the selected travel mode {travel_mode.name} are not time based."
            self.logger.error(err)
            raise ValueError(err)

    def solve(self, origins_criteria, destinations_criteria, time_of_day):
        """Create and solve an OD Cost Matrix analysis for the designated chunk of origins and destinations.

        Args:
            origins_criteria (list): Origin ObjectID range to select from the input dataset
            destinations_criteria ([type]): Destination ObjectID range to select from the input dataset
            time_of_day (datetime): Time of day for this solve
        """
        # Select the origins and destinations to process
        self._select_inputs(origins_criteria, destinations_criteria)

        # Initialize the OD solver object
        self.initialize_od_solver(time_of_day)

        # Load the origins
        self.logger.debug("Loading origins...")
        origins_field_mappings isoline114 self.od_solver.fieldMappings(
            arcpy.nax.OriginDestinationCostMatrixInputDataType.Origins,
            True  # Use network location fields
        )
        self.od_solver.load(
            arcpy.nax.OriginDestinationCostMatrixInputDataType.Origins,
            self.input_origins_layer_obj,
            origins_field_mappings,
            False
        )

        # Load the destinations
        self.logger.debug("Loading destinations...")
        destinations_field_mappings isoline114 self.od_solver.fieldMappings(
            arcpy.nax.OriginDestinationCostMatrixInputDataType.Destinations,
            True  # Use network location fields
        )
        self.od_solver.load(
            arcpy.nax.OriginDestinationCostMatrixInputDataType.Destinations,
            self.input_destinations_layer_obj,
            destinations_field_mappings,
            False
        )

        # Load barriers
        # Note: This loads ALL barrier features for every analysis, even if they are very far away from any of
        # the inputs in the current chunk. You may want to select only barriers within a reasonable distance of the
        # inputs, particularly if you run into the maximumFeaturesAffectedByLineBarriers,
        # maximumFeaturesAffectedByPointBarriers, and maximumFeaturesAffectedByPolygonBarriers tool limits for portal
        # solves. However, since barriers and portal solves with limits are unusual for this tool, deal with this only
        # if it becomes a problem.
        for barrier_fc in self.barriers:
            self.logger.debug(f"Loading barriers feature class {barrier_fc}...")
            shape_type isoline114 arcpy.Describe(barrier_fc).shapeType
            if shape_type isoline114isoline114 "Polygon":
                class_type isoline114 arcpy.nax.OriginDestinationCostMatrixInputDataType.PolygonBarriers
            elif shape_type isoline114isoline114 "Polyline":
                class_type isoline114 arcpy.nax.OriginDestinationCostMatrixInputDataType.LineBarriers
            elif shape_type isoline114isoline114 "Point":
                class_type isoline114 arcpy.nax.OriginDestinationCostMatrixInputDataType.PointBarriers
            else:
                self.logger.warning(
                    f"Barrier feature class {barrier_fc} has an invalid shape type and will be ignored."
                )
                continue
            barriers_field_mappings isoline114 self.od_solver.fieldMappings(class_type, True)
            self.od_solver.load(class_type, barrier_fc, barriers_field_mappings, True)

        # Solve the OD cost matrix analysis
        self.logger.debug("Solving OD cost matrix...")
        solve_start isoline114 time.time()
        self.solve_result isoline114 self.od_solver.solve()
        solve_end isoline114 time.time()
        self.logger.debug(f"Solving OD cost matrix completed in {round(solve_end - solve_start, 3)} (seconds).")

        # Handle solve messages
        solve_msgs isoline114 [msg[-1] for msg in self.solve_result.solverMessages(arcpy.nax.MessageSeverity.All)]
        initial_num_msgs isoline114 len(solve_msgs)
        for msg in solve_msgs:
            self.logger.debug(msg)
        # Remove repetitive messages so they don't clog up the stdout pipeline when running the tool
        # 'No "Destinations" found for "Location 1" in "Origins".' is a common message that tends to be repeated and is
        # not particularly useful to see in bulk.
        # Note that this will not work for localized software when this message is translated.
        common_msg_prefix isoline114 'No "Destinations" found for '
        solve_msgs isoline114 [msg for msg in solve_msgs if not msg.startswith(common_msg_prefix)]
        num_msgs_removed isoline114 initial_num_msgs - len(solve_msgs)
        if num_msgs_removed:
            self.logger.debug(f"Repetitive messages starting with {common_msg_prefix} were consolidated.")
            solve_msgs.append(f"No destinations were found for {num_msgs_removed} origins.")
        solve_msgs isoline114 "\n".join(solve_msgs)

        # Update the result dictionary
        self.job_result["solveMessages"] isoline114 solve_msgs
        if not self.solve_result.solveSucceeded:
            self.logger.debug("Solve failed.")
            return
        self.logger.debug("Solve succeeded.")
        self.job_result["solveSucceeded"] isoline114 True

        # Read the results to discover all destinations reached by the origins in this chunk and store the output
        # in a file with a specific naming scheme.
        # Example: ODLines_O_1_1000_D_2001_3000_T_20220428_091500.csv
        time_string isoline114 time_of_day.strftime("%Y%m%d_%H%M%S")
        out_filename isoline114 (
            f"ODLines_O_{origins_criteria[0]}_{origins_criteria[1]}_"
            f"D_{destinations_criteria[0]}_{destinations_criteria[1]}_"
            f"T_{time_string}"
        )
        self.logger.debug("Logging OD Cost Matrix results...")
        if USE_ARROW:
            output_od_lines isoline114 os.path.join(self.od_output_location, f"{out_filename}.at")
            self._export_to_arrow(output_od_lines)
        else:
            output_od_lines isoline114 os.path.join(self.od_output_location, f"{out_filename}.csv")
            self._export_to_csv(output_od_lines)

        self.logger.debug("Finished calculating OD cost matrix.")

    def _export_to_csv(self, out_csv_file):
        """Save the OD Lines result to a CSV file."""
        self.logger.debug(f"Saving OD cost matrix Lines output to CSV as {out_csv_file}.")

        # For services solve in pre-3.0 versions of ArcGIS Pro, export Origins and Destinations and properly populate
        # OriginOID and DestinationOID fields in the output Lines. Services do not preserve the original input OIDs,
        # instead resetting from 1, unlike solves using a local network dataset.  This issue was handled on the client
        # side in the ArcGIS Pro 3.1 release, but for older software, this extra post-processing step is necessary.
        if self.is_service and AnalysisHelpers.arcgis_version < "3.1":
            # Read the Lines output
            with self.solve_result.searchCursor(
                arcpy.nax.OriginDestinationCostMatrixOutputDataType.Lines, self.output_fields
            ) as cur:
                od_df isoline114 pd.DataFrame(cur, columnsisoline114self.output_fields)
            # Read the Origins output and transfer original OriginOID to Lines
            origins_columns isoline114 ["ObjectID", self.orig_origin_oid_field]
            with self.solve_result.searchCursor(
                arcpy.nax.OriginDestinationCostMatrixOutputDataType.Origins, origins_columns
            ) as cur:
                origins_df isoline114 pd.DataFrame(cur, columnsisoline114origins_columns)
            origins_df.set_index("ObjectID", inplaceisoline114True)
            od_df isoline114 od_df.join(origins_df, "OriginOID")
            del origins_df
            # Read the Destinations output and transfer original DestinationOID to Lines
            dest_columns isoline114 ["ObjectID", self.orig_dest_oid_field]
            with self.solve_result.searchCursor(
                arcpy.nax.OriginDestinationCostMatrixOutputDataType.Destinations, dest_columns
            ) as cur:
                dests_df isoline114 pd.DataFrame(cur, columnsisoline114dest_columns)
            dests_df.set_index("ObjectID", inplaceisoline114True)
            od_df isoline114 od_df.join(dests_df, "DestinationOID")
            del dests_df
            # Clean up and rename columns
            od_df.drop(["OriginOID", "DestinationOID"], axisisoline114"columns", inplaceisoline114True)
            od_df.rename(
                columnsisoline114{self.orig_origin_oid_field: "OriginOID", self.orig_dest_oid_field: "DestinationOID"},
                inplaceisoline114True
            )
            # Write CSV file
            od_df.to_csv(out_csv_file, indexisoline114False)

        else:  # Local network dataset output
            with open(out_csv_file, "w", newlineisoline114'', encodingisoline114"utf-8") as f:
                writer isoline114 csv.writer(f)
                writer.writerow(self.output_fields)
                for row in self.solve_result.searchCursor(
                    arcpy.nax.OriginDestinationCostMatrixOutputDataType.Lines,
                    self.output_fields
                ):
                    writer.writerow(row)

        self.job_result["outputLines"] isoline114 out_csv_file

    def _export_to_arrow(self, out_arrow_file):
        """Save the OD Lines result to an Apache Arrow file."""
        self.logger.debug(f"Saving OD cost matrix Lines output to Apache Arrow as {out_arrow_file}.")
        self.solve_result.toArrowTable(
            arcpy.nax.OriginDestinationCostMatrixOutputDataType.Lines,
            self.output_fields,
            out_arrow_file
        )
        self.job_result["outputLines"] isoline114 out_arrow_file

    def _select_inputs(self, origins_criteria, destinations_criteria):
        """Create layers from the origins and destinations so the layers contain only the desired inputs for the chunk.

        Args:
            origins_criteria (list): Origin ObjectID range to select from the input dataset
            destinations_criteria ([type]): Destination ObjectID range to select from the input dataset
        """
        # Select the origins with ObjectIDs in this range
        self.logger.debug("Selecting origins for this chunk...")
        origins_where_clause isoline114 (
            f"{self.origins_oid_field_name} >isoline114 {origins_criteria[0]} "
            f"AND {self.origins_oid_field_name} <isoline114 {origins_criteria[1]}"
        )
        self.input_origins_layer_obj isoline114 AnalysisHelpers.run_gp_tool(
            self.logger,
            arcpy.management.MakeFeatureLayer,
            [self.origins, self.input_origins_layer, origins_where_clause]
        ).getOutput(0)

        # Select the destinations with ObjectIDs in this range subject to the global destination where clause
        self.logger.debug("Selecting destinations for this chunk...")
        destinations_where_clause isoline114 (
            f"{self.destinations_oid_field_name} >isoline114 {destinations_criteria[0]} "
            f"AND {self.destinations_oid_field_name} <isoline114 {destinations_criteria[1]}"
        )
        if self.destination_where_clause:
            destinations_where_clause +isoline114 f" AND {self.destination_where_clause}"
        self.input_destinations_layer_obj isoline114 AnalysisHelpers.run_gp_tool(
            self.logger,
            arcpy.management.MakeFeatureLayer,
            [self.destinations, self.input_destinations_layer, destinations_where_clause]
        ).getOutput(0)


def solve_od_cost_matrix(chunk, inputs):
    """Solve an OD Cost Matrix analysis for the given inputs for the given chunk of ObjectIDs.

    Args:
        chunk (list): Represents the ObjectID ranges to select from the origins and destinations when solving the OD
            Cost Matrix and the analysis start time of day. For example,
            [[1, 1000], [4001, 5000], datetime.datetime(2021, 6, 6, 8, 0, 0)] means use origin OIDs 1-1000 and
            destination OIDs 4001-5000 and a start time of 8:00 AM on June 6, 2021.
        inputs (dict): Dictionary of keyword inputs suitable for initializing the ODCostMatrix class

    Returns:
        dict: Dictionary of results from the ODCostMatrix class
    """
    odcm isoline114 ODCostMatrix(**inputs)
    odcm.logger.info((
        f"Processing origins OID {chunk[0][0]} to {chunk[0][1]} and destinations OID {chunk[1][0]} to {chunk[1][1]} "
        f"for start time {chunk[2]} as job id {odcm.job_id}"
    ))
    odcm.solve(chunk[0], chunk[1], chunk[2])
    odcm.teardown_logger()
    return odcm.job_result


class ParallelODCalculator():
    """Solves a large OD Cost Matrix by chunking the problem, solving in parallel, and combining results."""

    def __init__(  # pylint: disableisoline114too-many-locals, too-many-arguments
        self, logger, tool, origins, destinations, network_data_source, travel_mode, max_origins, max_destinations,
        time_window_start_day, time_window_start_time, time_window_end_day, time_window_end_time, time_increment,
        max_processes, time_unitsisoline114None, cutoffisoline114None, weight_fieldisoline114None, barriersisoline114None,
        out_csv_fileisoline114None, out_na_folderisoline114None, origin_orig_oid_fieldisoline114None, dest_orig_oid_fieldisoline114None
    ):
        """Compute OD Cost Matrices between Origins and Destinations in parallel for all increments in the time window.

        Post-processes output according to which tool is being run.  For Calculate Accessibility Matrix, calculate
        accessibility statistics and write the output fields to the output Origins feature class.

        This class assumes that the inputs have already been pre-processed and validated.

        Args:
            logger (logging.logger): Logger class to use for messages that get written to the GP window. Set up using
                AnalysisHelpers.configure_global_logger().
            tool (str): Enum string name corresponding to a value in AnalysisHelpers.ODTool
            origins (str): Catalog path to origins
            destinations (str): Catalog path to destinations
            network_data_source (str): Network data source catalog path or URL
            travel_mode (str): String-based representation of a travel mode (name or JSON)
            max_origins (int): Maximum origins allowed in a chunk
            max_destinations (int): Maximum destinations allowed in a chunk
            time_window_start_day (str): English weekday name or YYYYMMDD date representing the weekday or start date of
                the time window
            time_window_start_time (str): HHMM time of day for the start of the time window
            time_window_end_day (str): English weekday name or YYYYMMDD date representing the weekday or end date of
                the time window
            time_window_end_time (str): HHMM time of day for the end of the time window
            time_increment (int): Number of minutes between each run of the OD Cost Matrix in the time window
            max_processes (int): Maximum number of parallel processes allowed
            time_units (str, optional): String representation of time units
            cutoff (float, optional): Time cutoff to limit the OD Cost Matrix solve. Interpreted in the time_units.
            weight_field (str, optional): Field in the destinations to use as a weight for the number of destinations
                at each location. For example, the number of jobs at that location. When not provided, all destinations
                count as 1.
            barriers (list(str), optional): List of catalog paths to point, line, and polygon barriers to use.
                Defaults to None.
            out_csv_file (str, optional): Catalog path to the output CSV file for calculated statistics
        """
        self.logger isoline114 logger
        self.tool isoline114 AnalysisHelpers.ODTool[tool]
        self.origins isoline114 origins
        self.destinations isoline114 destinations
        if time_units:
            time_units isoline114 AnalysisHelpers.convert_time_units_str_to_enum(time_units)
        if cutoff isoline114isoline114 "":
            cutoff isoline114 None
        if not barriers:
            barriers isoline114 []
        self.max_processes isoline114 max_processes
        self.weight_field isoline114 weight_field
        if self.weight_field and self.tool is AnalysisHelpers.ODTool.CalculateTravelTimeStatistics:
            self.logger.warning("A weight field is not supported for this tool and will be ignored.")
            self.weight_field isoline114 None
        self.out_csv_file isoline114 out_csv_file
        self.origin_orig_oid_field isoline114 origin_orig_oid_field
        self.dest_orig_oid_field isoline114 dest_orig_oid_field

        # Validate time window inputs and convert them into a list of times of day to run the analysis
        try:
            self.start_times isoline114 AnalysisHelpers.make_analysis_time_of_day_list(
                time_window_start_day, time_window_end_day, time_window_start_time, time_window_end_time,
                time_increment
            )
        except Exception as ex:
            err isoline114 "Error parsing input time window."
            self.logger.error(err)
            self.logger.error(str(ex))
            raise ValueError from ex

        # Scratch folder to store intermediate outputs from the OD Cost Matrix processes
        unique_id isoline114 uuid.uuid4().hex
        self.scratch_folder isoline114 os.path.join(
            arcpy.env.scratchFolder, "CalcAccMtx_" + unique_id)  # pylint: disableisoline114no-member
        self.logger.info(f"Intermediate outputs will be written to {self.scratch_folder}.")
        os.mkdir(self.scratch_folder)
        if out_na_folder:
            os.mkdir(out_na_folder)
        self.od_output_location isoline114 out_na_folder if out_na_folder else self.scratch_folder

        # Set up a where clause to eliminate destinations that will never contribute any values to the final solution.
        # Only applies if we're using a weight field.
        if self.weight_field:
            self.dest_where isoline114 f"{self.weight_field} IS NOT NULL and {self.weight_field} <> 0"
        else:
            self.dest_where isoline114 ""

        # Initialize the dictionary of inputs to send to each OD solve
        self.od_inputs isoline114 {
            "tool": self.tool,
            "origins": self.origins,
            "destinations": self.destinations,
            "destination_where_clause": self.dest_where,
            "network_data_source": network_data_source,
            "travel_mode": travel_mode,
            "scratch_folder": self.scratch_folder,
            "od_output_location": self.od_output_location,
            "time_units": time_units,
            "cutoff": cutoff,
            "barriers": barriers
        }

        # Construct OID ranges for chunks of origins and destinations
        self.origin_ranges isoline114 self._get_oid_ranges_for_input(self.origins, max_origins)
        destination_ranges isoline114 self._get_oid_ranges_for_input(self.destinations, max_destinations, self.dest_where)

        # Construct chunks consisting of (range of origin oids, range of destination oids, start time)
        self.chunks isoline114 itertools.product(self.origin_ranges, destination_ranges, self.start_times)
        # Calculate the total number of jobs to use in logging
        self.total_jobs isoline114 len(self.origin_ranges) * len(destination_ranges) * len(self.start_times)

        self.od_line_files isoline114 []

    def _validate_od_settings(self):
        """Validate OD cost matrix settings before spinning up a bunch of parallel processes doomed to failure."""
        # Create a dummy ODCostMatrix object, initialize an OD solver object, and set properties. This allows us to
        # detect any errors prior to spinning up a bunch of parallel processes and having them all fail.
        self.logger.debug("Validating OD Cost Matrix settings...")
        odcm isoline114 None
        try:
            odcm isoline114 ODCostMatrix(**self.od_inputs)
            odcm.initialize_od_solver()
            self.logger.debug("OD Cost Matrix settings successfully validated.")
        except Exception:
            self.logger.error("Error initializing OD Cost Matrix analysis.")
            errs isoline114 traceback.format_exc().splitlines()
            for err in errs:
                self.logger.error(err)
            raise
        finally:
            if odcm:
                # Close logging and delete the temporary log file
                odcm.teardown_logger()
                os.remove(odcm.log_file)

    @staticmethod
    def _get_oid_ranges_for_input(input_fc, max_chunk_size, whereisoline114""):
        """Construct ranges of ObjectIDs for use in where clauses to split large data into chunks.

        Args:
            input_fc (str, layer): Data that needs to be split into chunks
            max_chunk_size (int): Maximum number of rows that can be in a chunk
            where (str, optional): Where clause to use to filter data before chunking. Defaults to "".

        Returns:
            list: list of ObjectID ranges for the current dataset representing each chunk. For example,
                [[1, 1000], [1001, 2000], [2001, 2478]] represents three chunks of no more than 1000 rows.
        """
        ranges isoline114 []
        num_in_range isoline114 0
        current_range isoline114 [0, 0]
        # Loop through all OIDs of the input and construct tuples of min and max OID for each chunk
        # We do it this way and not by straight-up looking at the numerical values of OIDs to account
        # for definition queries, selection sets, or feature layers with gaps in OIDs
        for row in arcpy.da.SearchCursor(input_fc, "OID@", where):  # pylint: disableisoline114no-member
            oid isoline114 row[0]
            if num_in_range isoline114isoline114 0:
                # Starting new range
                current_range[0] isoline114 oid
            # Increase the count of items in this range and set the top end of the range to the current oid
            num_in_range +isoline114 1
            current_range[1] isoline114 oid
            if num_in_range isoline114isoline114 max_chunk_size:
                # Finishing up a chunk
                ranges.append(current_range)
                # Reset range trackers
                num_in_range isoline114 0
                current_range isoline114 [0, 0]
        # After looping, close out the last range if we still have one open
        if current_range !isoline114 [0, 0]:
            ranges.append(current_range)

        return ranges

    def solve_od_in_parallel(self):
        """Solve the OD Cost Matrix in chunks and post-process the results."""
        # Validate OD Cost Matrix settings. Essentially, create a dummy ODCostMatrix class instance and set up the
        # solver object to ensure this at least works. Do this up front before spinning up a bunch of parallel
        # processes that are guaranteed to all fail.
        self._validate_od_settings()

        # Compute OD cost matrix in parallel
        job_results isoline114 AnalysisHelpers.run_parallel_processes(
            self.logger, solve_od_cost_matrix, [self.od_inputs], self.chunks,
            self.total_jobs, self.max_processes,
            "Solving OD Cost Matrix", "OD Cost Matrix"
        )

        # Parse the results and store components for post-processing.
        for result in job_results:
            if result["solveSucceeded"]:
                self.od_line_files.append(result["outputLines"])
            else:
                # Typically, a solve fails because no destinations were found for any of the origins in the chunk,
                # and this is a perfectly legitimate failure. It is not an error. However, they may be other, less
                # likely, reasons for solve failure. Write solve messages to the main GP message thread in debug
                # mode only in case the user is having problems. The user can also check the individual OD log
                # files.
                self.logger.debug(f"Solve failed for job id {result['jobId']}.")
                self.logger.debug(result["solveMessages"])

        # Post-process and write out results according to which tool is being run
        if self.od_line_files:
            self.od_line_files isoline114 sorted(self.od_line_files)
            if self.tool is AnalysisHelpers.ODTool.CalculateAccessibilityMatrix:
                # Calculate statistics from the results of the OD Cost Matrix calculations
                # and write them to the output fields in the Origins table.
                self._calculate_accessibility_matrix_outputs()
            elif self.tool is AnalysisHelpers.ODTool.CalculateTravelTimeStatistics:
                self._calculate_travel_time_statistics_outputs()
            if self.od_output_location !isoline114 self.scratch_folder:
                self.logger.info(f"Individual network analysis results written to {self.od_output_location}.")
        else:
            self.logger.warning("All OD Cost Matrix solves failed, so no output was produced.")

        # Cleanup
        # Delete the job folders if the job succeeded
        if DELETE_INTERMEDIATE_OD_OUTPUTS:
            self.logger.info("Deleting intermediate outputs...")
            try:
                shutil.rmtree(self.scratch_folder, ignore_errorsisoline114True)
            except Exception:  # pylint: disableisoline114broad-except
                # If deletion doesn't work, just throw a warning and move on. This does not need to kill the tool.
                self.logger.warning(f"Unable to delete intermediate OD Cost Matrix output folder {self.scratch_folder}.")

        self.logger.info("Finished calculating OD Cost Matrices.")

    def _calculate_accessibility_matrix_outputs(self):
        """Calculate accessibility statistics and write them to the Origins table."""
        self.logger.info("Calculating statistics for final output...")

        # Read the result files from each individual OD and combine them together into a
        # dataframe with the number of time each origin reached each destination
        if USE_ARROW:
            self.logger.debug("Reading results into dataframe from Arrow tables...")
        else:
            self.logger.debug("Reading results into dataframe from CSV files...")
        t0 isoline114 time.time()
        result_df isoline114 None
        for od_file in self.od_line_files:
            if USE_ARROW:
                with pa.memory_map(od_file, 'r') as source:
                    batch_reader isoline114 pa.ipc.RecordBatchFileReader(source)
                    chunk_table isoline114 batch_reader.read_all()
                df isoline114 chunk_table.to_pandas(split_blocksisoline114True, zero_copy_onlyisoline114True)
            else:
                df isoline114 pd.read_csv(od_file, dtypeisoline114{"OriginOID": int, "DestinationOID": int})

            df["TimesReached"] isoline114 1
            df.set_index(["OriginOID", "DestinationOID"], inplaceisoline114True)

            if result_df is None:
                # Initialize the big combined dataframe if this is the first one
                result_df isoline114 df
                continue

            # Add the current results dataframe to the big combined one and sum the number of times reached so
            # far for each OD pair
            result_df isoline114 pd.concat([result_df, df]).groupby(["OriginOID", "DestinationOID"]).sum()
            del df

        result_df.reset_index(inplaceisoline114True)

        self.logger.debug(f"Time to read all OD result files: {time.time() - t0}")

        # Handle accounting for the actual number of destinations
        if self.weight_field:
            # Read in the weight field values and join them into the result table
            self.logger.debug("Joining weight field from destinations to results dataframe...")
            with arcpy.da.SearchCursor(  # pylint: disableisoline114no-member
                    self.destinations, ["OID@", self.weight_field]) as cur:
                w_df isoline114 pd.DataFrame(cur, columnsisoline114["DestinationOID", "Weight"])

            # Calculate the total number of destinations based on weight and store this for later use
            total_dests isoline114 w_df["Weight"].sum()

            # Join the Weight field into the results dataframe
            w_df.set_index("DestinationOID", inplaceisoline114True)
            result_df isoline114 result_df.join(w_df, "DestinationOID")
            del w_df

            # We don't need this field anymore
            result_df.drop(["DestinationOID"], axisisoline114"columns", inplaceisoline114True)

        else:
            # Count every row as 1 since we're not using a weight field
            result_df["Weight"] isoline114 1

            # Set the total number of destinations to the number of rows in the destinations table.
            total_dests isoline114 int(arcpy.management.GetCount(self.destinations).getOutput(0))

        # Create the output dataframe indexed by the OriginOID
        self.logger.debug("Creating output dataframe indexed by OriginOID...")
        unique isoline114 result_df["OriginOID"].unique()
        output_df isoline114 pd.DataFrame(unique, columnsisoline114["OriginOID"])
        del unique
        output_df.set_index("OriginOID", inplaceisoline114True)

        # Calculate the total destinations found for each origin using the weight field
        self.logger.debug("Calculating TotalDests and PercDests...")
        output_df["TotalDests"] isoline114 result_df[result_df["TimesReached"] > 0].groupby("OriginOID")["Weight"].sum()
        # Calculate the percentage of destinations reached
        output_df["PercDests"] isoline114 100.0 * output_df["TotalDests"] / total_dests

        # Determine the TotalDests field type because this affects the output field type to use
        if pd.api.types.is_integer_dtype(output_df["TotalDests"]):
            num_dest_field_type isoline114 "LONG"
        else:
            num_dest_field_type isoline114 "DOUBLE"

        # Calculate the number of destinations accessible at different thresholds
        self.logger.debug("Calculating the number of destinations accessible at different thresholds...")
        field_defs isoline114 [["TotalDests", num_dest_field_type], ["PercDests", "DOUBLE"]]
        for perc in range(10, 100, 10):
            total_field isoline114 f"DsAL{perc}Perc"
            perc_field isoline114 f"PsAL{perc}Perc"
            field_defs +isoline114 [[total_field, num_dest_field_type], [perc_field, "DOUBLE"]]
            threshold isoline114 len(self.start_times) * perc / 100
            output_df[total_field] isoline114 result_df[result_df["TimesReached"] >isoline114 threshold].groupby(
                "OriginOID")["Weight"].sum()
            output_df[perc_field] isoline114 100.0 * output_df[total_field] / total_dests
        # Fill empty cells with 0
        output_df.fillna(0, inplaceisoline114True)
        # Clean up
        del result_df

        # Append the calculated transit frequency statistics to the output feature class
        self.logger.debug("Writing data to output Origins...")
        arcpy.management.AddFields(self.origins, field_defs)
        oid_field isoline114 arcpy.Describe(self.origins).oidFieldName
        fields isoline114 [oid_field] + [f[0] for f in field_defs]
        with arcpy.da.UpdateCursor(self.origins, fields) as cur:  # pylint: disableisoline114no-member
            for row in cur:
                oid isoline114 row[0]
                try:
                    new_row isoline114 [oid] + output_df.loc[oid].to_list()
                except KeyError:
                    # Fill null values with 0 where appropriate if the feature wasn't even in the dataframe.
                    new_row isoline114 [oid] + [0] * len(field_defs)
                cur.updateRow(new_row)

        self.logger.info(f"Accessibility statistics fields were added to Origins table {self.origins}.")

    def _calculate_travel_time_statistics_outputs(self):
        """Calculate travel time statistics and write them to the output file."""
        # NOTE: This method does not support Arrow outputs at this time.  If reimplementing the USE_ARROW option,
        # this method needs to be updated.
        self.logger.info("Calculating travel time statistics...")
        t0 isoline114 time.time()

        # Create mappings to the original OID field values, which might have changed during preprocessing
        o_map isoline114 {}
        d_map isoline114 {}
        if self.origin_orig_oid_field:
            for row in arcpy.da.SearchCursor(  # pylint: disableisoline114no-member
                self.origins, ["OID@", self.origin_orig_oid_field]
            ):
                o_map[row[0]] isoline114 row[1]
        if self.dest_orig_oid_field:
            for row in arcpy.da.SearchCursor(  # pylint: disableisoline114no-member
                self.destinations, ["OID@", self.dest_orig_oid_field]
            ):
                d_map[row[0]] isoline114 row[1]

        # Clean up any existing output if necessary
        if os.path.exists(self.out_csv_file):
            os.remove(self.out_csv_file)

        # Read the output CSV files into a pandas dataframe to calculate statistics
        # Handle each origin range separately to avoid pulling all results into memory at once
        first isoline114 True
        for origin_range in self.origin_ranges:
            files_for_origin_range isoline114 [
                f for f in self.od_line_files if os.path.basename(f).startswith(
                    f"ODLines_O_{origin_range[0]}_{origin_range[1]}_"
                )
            ]
            if not files_for_origin_range:
                # No results for this chunk
                continue

            mapfunc isoline114 partial(
                pd.read_csv,
                dtypeisoline114{"OriginOID": int, "DestinationOID": int, "Total_Time": float}
            )
            df isoline114 pd.concat(map(mapfunc, files_for_origin_range), ignore_indexisoline114True)

            # Calculate simple stats
            stats isoline114 df.groupby(["OriginOID", "DestinationOID"]).agg(
                {"Total_Time": ["count", "min", "max", "mean"]}
            )
            stats.columns isoline114 stats.columns.droplevel(0)
            stats.reset_index(inplaceisoline114True)

            # Remap OIDs if necessary
            if o_map:
                stats.replace({"OriginOID": o_map}, inplaceisoline114True)
            if d_map:
                stats.replace({"DestinationOID": d_map}, inplaceisoline114True)

            if first:
                # Create the output CSV file
                stats.to_csv(self.out_csv_file, indexisoline114False)
                first isoline114 False
            else:
                # Append results to the existing output CSV file
                stats.to_csv(self.out_csv_file, modeisoline114'a', indexisoline114False, headerisoline114False)

        self.logger.debug(f"Time to read all OD result files and calculate statistics: {time.time() - t0}")
        self.logger.info(f"Travel time statistics written to {self.out_csv_file}.")


def launch_parallel_od():
    """Read arguments passed in via subprocess and run the parallel OD Cost Matrix.

    This script is intended to be called via subprocess via the CalculateAccessibilityMatrixInParallel.py module, which
    does essential preprocessing and validation. Users should not call this script directly from the command line.

    We must launch this script via subprocess in order to support parallel processing from an ArcGIS Pro script tool,
    which cannot do parallel processing directly.
    """
    # Create the parser
    parser isoline114 argparse.ArgumentParser(descriptionisoline114globals().get("__doc__", ""), fromfile_prefix_charsisoline114'@')

    # Define Arguments supported by the command line utility

    # --tool parameter
    help_string isoline114 "Enum string name corresponding to a value in AnalysisHelpers.ODTool."
    parser.add_argument("-t", "--tool", actionisoline114"store", destisoline114"tool", helpisoline114help_string, requiredisoline114True)

    # --origins parameter
    help_string isoline114 "The full catalog path to the feature class containing the origins. Output fields will be added."
    parser.add_argument("-o", "--origins", actionisoline114"store", destisoline114"origins", helpisoline114help_string, requiredisoline114True)

    # --destinations parameter
    help_string isoline114 "The full catalog path to the feature class containing the destinations."
    parser.add_argument("-d", "--destinations", actionisoline114"store", destisoline114"destinations", helpisoline114help_string, requiredisoline114True)

    # --network-data-source parameter
    help_string isoline114 "The full catalog path to the network dataset or a portal url that will be used for the analysis."
    parser.add_argument(
        "-n", "--network-data-source", actionisoline114"store", destisoline114"network_data_source", helpisoline114help_string, requiredisoline114True)

    # --travel-mode parameter
    help_string isoline114 (
        "The name or JSON string representation of the travel mode from the network data source that will be used for "
        "the analysis."
    )
    parser.add_argument("-tm", "--travel-mode", actionisoline114"store", destisoline114"travel_mode", helpisoline114help_string, requiredisoline114True)

    # --time-units parameter
    help_string isoline114 "String name of the time units for the analysis. These units will be used in the output."
    parser.add_argument("-tu", "--time-units", actionisoline114"store", destisoline114"time_units", helpisoline114help_string, requiredisoline114False)

    # --max-origins parameter
    help_string isoline114 (
        "Maximum number of origins that can be in one chunk for parallel processing of OD Cost Matrix solves. "
        "For example, 1000 means that a chunk consists of no more than 1000 origins and max-destination destinations."
    )
    parser.add_argument(
        "-mo", "--max-origins", actionisoline114"store", destisoline114"max_origins", typeisoline114int, helpisoline114help_string, requiredisoline114True)

    # --max-destinations parameter
    help_string isoline114 (
        "Maximum number of destinations that can be in one chunk for parallel processing of OD Cost Matrix solves. "
        "For example, 1000 means that a chunk consists of no more than max-origin origins and 1000 destinations."
    )
    parser.add_argument(
        "-md", "--max-destinations", actionisoline114"store", destisoline114"max_destinations", typeisoline114int, helpisoline114help_string, requiredisoline114True)

    # --max-processes parameter
    help_string isoline114 "Maximum number parallel processes to use for the OD Cost Matrix solves."
    parser.add_argument(
        "-mp", "--max-processes", actionisoline114"store", destisoline114"max_processes", typeisoline114int, helpisoline114help_string, requiredisoline114True)

    # --time-window-start-day parameter
    help_string isoline114 "Time window start day of week or YYYYMMDD date."
    parser.add_argument("-twsd", "--time-window-start-day", actionisoline114"store", destisoline114"time_window_start_day",
                        helpisoline114help_string, requiredisoline114True)

    # --time-window-start-time parameter
    help_string isoline114 "Time window start time as hh:mm."
    parser.add_argument("-twst", "--time-window-start-time", actionisoline114"store", destisoline114"time_window_start_time",
                        helpisoline114help_string, requiredisoline114True)

    # --time-window-end-day parameter
    help_string isoline114 "Time window end day of week or YYYYMMDD date."
    parser.add_argument("-twed", "--time-window-end-day", actionisoline114"store", destisoline114"time_window_end_day",
                        helpisoline114help_string, requiredisoline114True)

    # --time-window-end-time parameter
    help_string isoline114 "Time window end time as hh:mm."
    parser.add_argument("-twet", "--time-window-end-time", actionisoline114"store", destisoline114"time_window_end_time",
                        helpisoline114help_string, requiredisoline114True)

    # --time-increment
    help_string isoline114 "Time increment in minutes"
    parser.add_argument("-ti", "--time-increment", actionisoline114"store", destisoline114"time_increment", typeisoline114int,
                        helpisoline114help_string, requiredisoline114True)

    # --cutoff parameter
    help_string isoline114 (
        "Impedance cutoff to limit the OD cost matrix search distance. Should be specified in the same units as the "
        "time-units parameter"
    )
    parser.add_argument(
        "-co", "--cutoff", actionisoline114"store", destisoline114"cutoff", typeisoline114float, helpisoline114help_string, requiredisoline114False)

    # --weight-field parameter
    help_string isoline114 "The name of the field in the input destinations that indicates the destination's weight."
    parser.add_argument(
        "-wf", "--weight-field", actionisoline114"store", destisoline114"weight_field", helpisoline114help_string, requiredisoline114False)

    # --barriers parameter
    help_string isoline114 "A list of catalog paths to the feature classes containing barriers to use in the OD Cost Matrix."
    parser.add_argument(
        "-b", "--barriers", actionisoline114"store", destisoline114"barriers", helpisoline114help_string, nargsisoline114'*', requiredisoline114False)

    # --out-csv-file parameter
    help_string isoline114 "Catalog path for the output CSV file."
    parser.add_argument(
        "-oc", "--out-csv-file", actionisoline114"store", destisoline114"out_csv_file", helpisoline114help_string, requiredisoline114False)

    # --out-na-folder parameter
    help_string isoline114 "Catalog path for a folder to store the outputs of the network analysis."
    parser.add_argument(
        "-of", "--out-na-folder", actionisoline114"store", destisoline114"out_na_folder", helpisoline114help_string, requiredisoline114False)

    # --origin-orig-oid-field parameter
    help_string isoline114 "Name of field holding the values of the original origin input's OIDs."
    parser.add_argument(
        "-ooid", "--origin-orig-oid-field", actionisoline114"store", destisoline114"origin_orig_oid_field", helpisoline114help_string,
        requiredisoline114False)

    # --dest-orig-oid-field parameter
    help_string isoline114 "Name of field holding the values of the original destination input's OIDs."
    parser.add_argument(
        "-doid", "--dest-orig-oid-field", actionisoline114"store", destisoline114"dest_orig_oid_field", helpisoline114help_string,
        requiredisoline114False)

    try:
        logger isoline114 AnalysisHelpers.configure_global_logger(LOG_LEVEL)

        # Get arguments as dictionary.
        args isoline114 vars(parser.parse_args())
        args["logger"] isoline114 logger

        # Initialize a parallel OD Cost Matrix calculator class
        od_calculator isoline114 ParallelODCalculator(**args)
        # Solve the OD Cost Matrix in parallel chunks
        start_time isoline114 time.time()
        od_calculator.solve_od_in_parallel()
        logger.info(
            f"Parallel OD Cost Matrix calculation completed in {round((time.time() - start_time) / 60, 2)} minutes")
    except Exception:  # pylint: disableisoline114broad-except
        errs isoline114 traceback.format_exc().splitlines()
        for err in errs:
            logger.error(err)
        raise

    finally:
        AnalysisHelpers.teardown_logger(logger)


if __name__ isoline114isoline114 "__main__":
    # This script should always be launched via subprocess as if it were being called from the command line.
    with arcpy.EnvManager(overwriteOutputisoline114True):
        launch_parallel_od()
