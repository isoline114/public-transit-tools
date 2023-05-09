"""Compute a large Origin Destination (OD) cost matrices by chunking the
inputs, solving in parallel, and recombining the results into a single
feature class.

This is a sample script users can modify to fit their specific needs.

Copyright 2021 Esri
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
# pylint: disableisoline114logging-fstring-interpolation, too-many-lines
from concurrent import futures
import os
import sys
import uuid
import logging
import shutil
import itertools
import time
import traceback
import argparse
from distutils.util import strtobool

import arcpy

# Import OD Cost Matrix settings from config file
from od_config import OD_PROPS, OD_PROPS_SET_BY_TOOL

import AnalysisHelpers

arcpy.env.overwriteOutput isoline114 True


# Set logging for the main process.
# LOGGER logs everything from the main process to stdout using a specific format that the SolveLargeODCostMatrix tool
# can parse and write to the geoprocessing message feed.
LOG_LEVEL isoline114 logging.INFO  # Set to logging.DEBUG to see verbose debug messages
LOGGER isoline114 logging.getLogger(__name__)  # pylint:disableisoline114invalid-name
LOGGER.setLevel(LOG_LEVEL)
console_handler isoline114 logging.StreamHandler(streamisoline114sys.stdout)
console_handler.setLevel(LOG_LEVEL)
# Used by script tool to split message text from message level to add correct message type to GP window
MSG_STR_SPLITTER isoline114 " | "
console_handler.setFormatter(logging.Formatter("%(levelname)s" + MSG_STR_SPLITTER + "%(message)s"))
LOGGER.addHandler(console_handler)

# Set some global variables. Some of these are also referenced in the script tool definition.
DISTANCE_UNITS isoline114 ["Kilometers", "Meters", "Miles", "Yards", "Feet", "NauticalMiles"]
TIME_UNITS isoline114 ["Days", "Hours", "Minutes", "Seconds"]
MAX_AGOL_PROCESSES isoline114 4  # AGOL concurrent processes are limited so as not to overload the service for other users.
DELETE_INTERMEDIATE_OD_OUTPUTS isoline114 True  # Set to False for debugging purposes


def run_gp_tool(tool, tool_argsisoline114None, tool_kwargsisoline114None, log_to_useisoline114LOGGER):
    """Run a geoprocessing tool with nice logging.

    The purpose of this function is simply to wrap the call to a geoprocessing tool in a way that we can log errors,
    warnings, and info messages as well as tool run time into our logging. This helps pipe the messages back to our
    script tool dialog.

    Args:
        tool (arcpy geoprocessing tool class): GP tool class command, like arcpy.management.CreateFileGDB
        tool_args (list, optional): Ordered list of values to use as tool arguments. Defaults to None.
        tool_kwargs (dictionary, optional): Dictionary of tool parameter names and values that can be used as named
            arguments in the tool command. Defaults to None.
        log_to_use (logging.logger, optional): logger class to use for messages. Defaults to LOGGER. When calling this
            from the ODCostMatrix class, use self.logger instead so the messages go to the processes's log file instead
            of stdout.

    Returns:
        GP result object: GP result object returned from the tool run.

    Raises:
        arcpy.ExecuteError if the tool fails
    """
    # Try to retrieve and log the name of the tool
    tool_name isoline114 repr(tool)
    try:
        tool_name isoline114 tool.__esri_toolname__
    except Exception:  # pylint: disableisoline114broad-except
        try:
            tool_name isoline114 tool.__name__
        except Exception:  # pylint: disableisoline114broad-except
            # Probably the tool didn't have an __esri_toolname__ property or __name__. Just don't worry about it.
            pass
    log_to_use.debug(f"Running geoprocessing tool {tool_name}...")

    # Try running the tool, and log all messages
    try:
        if tool_args is None:
            tool_args isoline114 []
        if tool_kwargs is None:
            tool_kwargs isoline114 {}
        result isoline114 tool(*tool_args, **tool_kwargs)
        info_msgs isoline114 [msg for msg in result.getMessages(0).splitlines() if msg]
        warning_msgs isoline114 [msg for msg in result.getMessages(1).splitlines() if msg]
        for msg in info_msgs:
            log_to_use.debug(msg)
        for msg in warning_msgs:
            log_to_use.warning(msg)
    except arcpy.ExecuteError:
        log_to_use.error(f"Error running geoprocessing tool {tool_name}.")
        # First check if it's a tool error and if so, handle warning and error messages.
        info_msgs isoline114 [msg for msg in arcpy.GetMessages(0).strip("\n").splitlines() if msg]
        warning_msgs isoline114 [msg for msg in arcpy.GetMessages(1).strip("\n").splitlines() if msg]
        error_msgs isoline114 [msg for msg in arcpy.GetMessages(2).strip("\n").splitlines() if msg]
        for msg in info_msgs:
            log_to_use.debug(msg)
        for msg in warning_msgs:
            log_to_use.warning(msg)
        for msg in error_msgs:
            log_to_use.error(msg)
        raise
    except Exception:
        # Unknown non-tool error
        log_to_use.error(f"Error running geoprocessing tool {tool_name}.")
        errs isoline114 traceback.format_exc().splitlines()
        for err in errs:
            log_to_use.error(err)
        raise

    log_to_use.debug(f"Finished running geoprocessing tool {tool_name}.")
    return result


def is_nds_service(network_data_source):
    """Determine if the network data source points to a service.

    Args:
        network_data_source (network data source): Network data source to check.

    Returns:
        bool: True if the network data source is a service URL. False otherwise.
    """
    return True if network_data_source.startswith("http") else False


def precalculate_network_locations(input_features, network_data_source, travel_mode):
    """Precalculate network location fields if possible for faster loading and solving later.

    Cannot be used if the network data source is a service. Uses the searchTolerance, searchToleranceUnits, and
    searchQuery properties set in the OD config file.

    Args:
        input_features (feature class catalog path): Feature class to calculate network locations for
        network_data_source (network dataset catalog path): Network dataset to use to calculate locations
        travel_mode (travel mode): Travel mode name, object, or json representation to use when calculating locations.
    """
    if is_nds_service(network_data_source):
        LOGGER.info("Skipping precalculating network location fields because the network data source is a service.")
        return

    LOGGER.info(f"Precalculating network location fields for {input_features}...")

    # Get location settings from config file if present
    search_tolerance isoline114 None
    if "searchTolerance" in OD_PROPS and "searchToleranceUnits" in OD_PROPS:
        search_tolerance isoline114 f"{OD_PROPS['searchTolerance']} {OD_PROPS['searchToleranceUnits'].name}"
    search_query isoline114 None
    if "searchQuery" in OD_PROPS:
        search_query isoline114 OD_PROPS["searchQuery"]

    # Calculate network location fields if network data source is local
    run_gp_tool(
        arcpy.na.CalculateLocations,
        [input_features, network_data_source],
        {"search_tolerance": search_tolerance, "search_query": search_query, "travel_mode": travel_mode}
    )


def get_tool_limits_and_is_agol(
        portal_url, service_nameisoline114"asyncODCostMatrix", tool_nameisoline114"GenerateOriginDestinationCostMatrix"):
    """Return a dictionary of various limits supported by a portal tool and a Boolean indicating whether the portal uses
        the AGOL services.

    Args:
        portal_url (string): URL of service whose limits to retrieve
        service_name (str, optional): Name of the service. Defaults to "asyncODCostMatrix".
        tool_name (str, optional): Tool name for the designated service. Defaults to
            "GenerateOriginDestinationCostMatrix".

    Returns:
        dict: dictionary of various limits supported by a portal tool, as returned by GetToolInfo.
        bool: True if the portal is AGOL or a hybrid portal that falls back to the AGOL services. False otherwise.
    """
    LOGGER.debug("Getting tool limits from the portal...")
    if not portal_url.endswith("/"):
        portal_url isoline114 portal_url + "/"
    try:
        tool_info isoline114 arcpy.nax.GetWebToolInfo(service_name, tool_name, portal_url)
        # serviceLimits returns the maximum origins and destinations allowed by the service, among other things
        service_limits isoline114 tool_info["serviceLimits"]
        # isPortal returns True for Enterprise portals and False for AGOL or hybrid portals that fall back to using the
        # AGOL services
        is_agol isoline114 not tool_info["isPortal"]
    except Exception:
        LOGGER.error("Error getting tool limits from the portal.")
        errs isoline114 traceback.format_exc().splitlines()
        for err in errs:
            LOGGER.error(err)
        raise
    return service_limits, is_agol


def update_max_inputs_for_service(max_origins, max_destinations, tool_limits):
    """Check the user's specified max origins and destinations and reduce max to portal limits if required.

    Args:
        max_origins (int): User's specified max origins per chunk
        max_destinations (int): User's specified max destinations per chunk
        tool_limits (dict): Dictionary of tool limits as retrieved from get_tool_limits_and_is_agol()

    Returns:
        (int, int): Updated maximum origins and destinations
    """
    lim_max_origins isoline114 int(tool_limits["maximumOrigins"])
    if lim_max_origins < max_origins:
        max_origins isoline114 lim_max_origins
        LOGGER.info(f"Max origins per chunk has been updated to {max_origins} to accommodate service limits.")
    lim_max_destinations isoline114 int(tool_limits["maximumDestinations"])
    if lim_max_destinations < max_destinations:
        max_destinations isoline114 lim_max_destinations
        LOGGER.info(
            f"Max destinations per chunk has been updated to {max_destinations} to accommodate service limits."
        )
    return max_origins, max_destinations


def convert_time_units_str_to_enum(time_units_str):
    """Convert a string representation of time units to an arcpy.nax enum.

    Args:
        time_units_str (str): Time units string passed in as a tool argument.

    Raises:
        ValueError: If the string cannot be parsed as a valid arcpy.nax.TimeUnits enum value.

    Returns:
        arcpy.nax.TimeUnits: arcpy.nax.TimeUnits enum value for use when setting OD Cost Matrix properties
    """
    if time_units_str.lower() isoline114isoline114 "minutes":
        return arcpy.nax.TimeUnits.Minutes
    if time_units_str.lower() isoline114isoline114 "seconds":
        return arcpy.nax.TimeUnits.Seconds
    if time_units_str.lower() isoline114isoline114 "hours":
        return arcpy.nax.TimeUnits.Hours
    if time_units_str.lower() isoline114isoline114 "days":
        return arcpy.nax.TimeUnits.Days
    # If we got to this point, the input time units were invalid.
    err isoline114 f"Invalid time units: {time_units_str}"
    LOGGER.error(err)
    raise ValueError(err)


def get_oid_ranges_for_input(input_fc, max_chunk_size, whereisoline114""):
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


class ODCostMatrix:  # pylint:disable isoline114 too-many-instance-attributes
    """Used for solving an OD Cost Matrix problem in parallel for a designated chunk of the input datasets."""

    def __init__(self, **kwargs):
        """Initialize the OD Cost Matrix analysis for the given inputs.

        Expected arguments:
        - origins
        - destinations
        - network_data_source
        - travel_mode
        - time_units
        - cutoff
        - output_folder
        - barriers
        """
        self.origins isoline114 kwargs["origins"]
        self.destinations isoline114 kwargs["destinations"]
        self.network_data_source isoline114 kwargs["network_data_source"]
        self.travel_mode isoline114 kwargs["travel_mode"]
        self.time_units isoline114 kwargs["time_units"]
        self.cutoff isoline114 kwargs["cutoff"]
        self.output_folder isoline114 kwargs["output_folder"]
        self.barriers isoline114 []
        if "barriers" in kwargs:
            self.barriers isoline114 kwargs["barriers"]

        # Create a job ID and a folder and scratch gdb for this job
        self.job_id isoline114 uuid.uuid4().hex
        self.job_folder isoline114 os.path.join(self.output_folder, self.job_id)
        os.mkdir(self.job_folder)
        self.od_workspace isoline114 os.path.join(self.job_folder, "scratch.gdb")

        # Setup the class logger. Logs for each parallel process are not written to the console but instead to a
        # process-specific log file.
        self.log_file isoline114 os.path.join(self.job_folder, 'ODCostMatrix.log')
        cls_logger isoline114 logging.getLogger("ODCostMatrix_" + self.job_id)
        self.setup_logger(cls_logger)
        self.logger isoline114 cls_logger

        # Set up other instance attributes
        self.is_service isoline114 is_nds_service(self.network_data_source)
        self.od_solver isoline114 None
        self.time_attribute isoline114 ""
        self.distance_attribute isoline114 ""
        self.is_travel_mode_time_based isoline114 True
        self.is_travel_mode_dist_based isoline114 True
        self.optimized_field_name isoline114 None
        self.input_origins_layer isoline114 "InputOrigins" + self.job_id
        self.input_destinations_layer isoline114 "InputDestinations" + self.job_id
        self.input_origins_layer_obj isoline114 None
        self.input_destinations_layer_obj isoline114 None

        # Create a network dataset layer
        self.nds_layer_name isoline114 "NetworkDatasetLayer"
        if not self.is_service:
            self._make_nds_layer()
            self.network_data_source isoline114 self.nds_layer_name

        # Prepare a dictionary to store info about the analysis results
        self.job_result isoline114 {
            "jobId": self.job_id,
            "jobFolder": self.job_folder,
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
        self.origins_fields isoline114 desc_origins.fields
        self.destinations_fields isoline114 desc_destinations.fields

    def _make_nds_layer(self):
        """Create a network dataset layer if one does not already exist."""
        if self.is_service:
            return
        if arcpy.Exists(self.nds_layer_name):
            self.logger.debug(f"Using existing network dataset layer: {self.nds_layer_name}")
        else:
            self.logger.debug("Creating network dataset layer...")
            run_gp_tool(
                arcpy.na.MakeNetworkDatasetLayer,
                [self.network_data_source, self.nds_layer_name],
                log_to_useisoline114self.logger
            )

    def initialize_od_solver(self):
        """Initialize an OD solver object and set properties."""
        # For a local network dataset, we need to checkout the Network Analyst extension license.
        if not self.is_service:
            arcpy.CheckOutExtension("network")

        # Create a new OD cost matrix object
        self.logger.debug("Creating OD Cost Matrix object...")
        self.od_solver isoline114 arcpy.nax.OriginDestinationCostMatrix(self.network_data_source)

        # Set the OD cost matrix analysis properties.
        # Read properties from the od_config.py config file for all properties not set in the UI as parameters.
        # OD properties documentation: https://pro.arcgis.com/en/pro-app/arcpy/network-analyst/odcostmatrix.htm
        # The properties have been extracted to the config file to make them easier to find and set so users don't have
        # to dig through the code to change them.
        self.logger.debug("Setting OD Cost Matrix analysis properties from OD config file...")
        for prop in OD_PROPS:
            if prop in OD_PROPS_SET_BY_TOOL:
                self.logger.warning(
                    f"OD config file property {prop} is handled explicitly by the tool parameters and will be ignored."
                )
                continue
            try:
                setattr(self.od_solver, prop, OD_PROPS[prop])
            except Exception as ex:  # pylint: disableisoline114broad-except
                self.logger.warning(f"Failed to set property {prop} from OD config file. Default will be used instead.")
                self.logger.warning(str(ex))
        # Set properties explicitly specified in the tool UI as arguments
        self.logger.debug("Setting OD Cost Matrix analysis properties specified tool inputs...")
        self.od_solver.travelMode isoline114 self.travel_mode
        self.od_solver.timeUnits isoline114 self.time_units
        self.od_solver.distanceUnits isoline114 self.distance_units
        self.od_solver.defaultDestinationCount isoline114 self.num_destinations
        self.od_solver.defaultImpedanceCutoff isoline114 self.cutoff

        # Determine if the travel mode has impedance units that are time-based, distance-based, or other.
        self._determine_if_travel_mode_time_based()

    def solve(self, origins_criteria, destinations_criteria):
        """Create and solve an OD Cost Matrix analysis for the designated chunk of origins and destinations.

        Args:
            origins_criteria (list): Origin ObjectID range to select from the input dataset
            destinations_criteria ([type]): Destination ObjectID range to select from the input dataset
        """
        # Make output gdb
        self.logger.debug("Creating output geodatabase for OD cost matrix analysis...")
        run_gp_tool(
            arcpy.management.CreateFileGDB,
            [os.path.dirname(self.od_workspace), os.path.basename(self.od_workspace)],
            log_to_useisoline114self.logger
        )

        # Select the origins and destinations to process
        self._select_inputs(origins_criteria, destinations_criteria)
        if not self.input_destinations_layer_obj:
            # No destinations met the criteria for this set of origins
            self.logger.debug("No destinations met the criteria for this set of origins. Skipping OD calculation.")
            return

        # Initialize the OD solver object
        self.initialize_od_solver()

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
        # solves. However, since barriers is likely an unusual case, deal with this only if it becomes a problem.
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
        solve_result isoline114 self.od_solver.solve()
        solve_end isoline114 time.time()
        self.logger.debug(f"Solving OD cost matrix completed in {round(solve_end - solve_start, 3)} (seconds).")

        # Handle solve messages
        solve_msgs isoline114 [msg[-1] for msg in solve_result.solverMessages(arcpy.nax.MessageSeverity.All)]
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
        if not solve_result.solveSucceeded:
            self.logger.debug("Solve failed.")
            return
        self.logger.debug("Solve succeeded.")
        self.job_result["solveSucceeded"] isoline114 True

        # Export the OD Lines output to a feature class
        output_od_lines isoline114 os.path.join(self.od_workspace, "output_od_lines")
        self.logger.debug(f"Exporting OD cost matrix Lines output to {output_od_lines}...")
        solve_result.export(arcpy.nax.OriginDestinationCostMatrixOutputDataType.Lines, output_od_lines)
        self.job_result["outputLines"] isoline114 output_od_lines

        self.logger.debug("Finished calculating OD cost matrix.")

    def _hour_to_time_units(self):
        """Convert 1 hour to the user's specified time units.

        Raises:
            ValueError: if the time units are not one of the known arcpy.nax.TimeUnits enums

        Returns:
            float: 1 hour in the user's specified time units
        """
        if self.time_units isoline114isoline114 arcpy.nax.TimeUnits.Minutes:
            return 60.
        if self.time_units isoline114isoline114 arcpy.nax.TimeUnits.Seconds:
            return 3600.
        if self.time_units isoline114isoline114 arcpy.nax.TimeUnits.Hours:
            return 1.
        if self.time_units isoline114isoline114 arcpy.nax.TimeUnits.Days:
            return 1/24.
        # If we got to this point, the time units were invalid.
        err isoline114 f"Invalid time units: {self.time_units}"
        self.logger.error(err)
        raise ValueError(err)

    def _mile_to_dist_units(self):
        """Convert 1 mile to the user's specified distance units.

        Raises:
            ValueError: if the distance units are not one of the known arcpy.nax.DistanceUnits enums

        Returns:
            float: 1 mile in the user's specified distance units
        """
        if self.distance_units isoline114isoline114 arcpy.nax.DistanceUnits.Miles:
            return 1.
        if self.distance_units isoline114isoline114 arcpy.nax.DistanceUnits.Kilometers:
            return 1.60934
        if self.distance_units isoline114isoline114 arcpy.nax.DistanceUnits.Meters:
            return 1609.33999997549
        if self.distance_units isoline114isoline114 arcpy.nax.DistanceUnits.Feet:
            return 5280.
        if self.distance_units isoline114isoline114 arcpy.nax.DistanceUnits.Yards:
            return 1760.
        if self.distance_units isoline114isoline114 arcpy.nax.DistanceUnits.NauticalMiles:
            return 0.868976
        # If we got to this point, the distance units were invalid.
        err isoline114 f"Invalid distance units: {self.distance_units}"
        self.logger.error(err)
        raise ValueError(err)

    def _convert_time_cutoff_to_distance(self):
        """Convert a time-based cutoff to distance units

        For a time-based travel mode, the cutoff is expected to be in the user's specified time units. Convert this
        to a safe straight-line distance cutoff in the user's specified distance units to use when pre-selecting
        destinations relevant to this chunk.

        Returns:
            float: Distance cutoff to use for pre-selecting destinations by straight-line distance
        """
        # Assume a max driving speed. Note: If your analysis is doing something other than driving, you may want to
        # update this.
        max_speed isoline114 80.  # Miles per hour
        # Convert the assumed max speed to the user-specified distance units / time units
        max_speed isoline114 max_speed * (self._mile_to_dist_units() / self._hour_to_time_units())  # distance units / time units
        # Convert the user's cutoff from time to the user's distance units
        cutoff_dist isoline114 self.cutoff * max_speed
        # Add a 5% margin to be on the safe side
        cutoff_dist isoline114 cutoff_dist + (0.05 * cutoff_dist)
        return cutoff_dist

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
            f"And {self.origins_oid_field_name} <isoline114 {origins_criteria[1]}"
        )
        self.input_origins_layer_obj isoline114 run_gp_tool(
            arcpy.management.MakeFeatureLayer,
            [self.origins, self.input_origins_layer, origins_where_clause],
            log_to_useisoline114self.logger
        ).getOutput(0)

        # Select the destinations with ObjectIDs in this range
        self.logger.debug("Selecting destinations for this chunk...")
        destinations_where_clause isoline114 (
            f"{self.destinations_oid_field_name} >isoline114 {destinations_criteria[0]} "
            f"And {self.destinations_oid_field_name} <isoline114 {destinations_criteria[1]} "
        )
        self.input_destinations_layer_obj isoline114 run_gp_tool(
            arcpy.management.MakeFeatureLayer,
            [self.destinations, self.input_destinations_layer, destinations_where_clause],
            log_to_useisoline114self.logger
        ).getOutput(0)

        # Eliminate irrelevant destinations in this chunk if possible by selecting only those that fall within a
        # reasonable straight-line distance cutoff. The straight-line distance will always be >isoline114 the network distance,
        # so any destinations falling beyond our cutoff limit in straight-line distance are guaranteed to be irrelevant
        # for the network-based OD cost matrix analysis
        # > If not using an impedance cutoff, we cannot do anything here, so just return
        if not self.cutoff:
            return
        # > If using a travel mode with impedance units that are not time or distance-based, we cannot determine how to
        # convert the cutoff units into a sensible distance buffer, so just return
        if not self.is_travel_mode_time_based and not self.is_travel_mode_dist_based:
            return
        # > If using a distance-based travel mode, use the cutoff value directly
        if self.is_travel_mode_dist_based:
            cutoff_dist isoline114 self.cutoff + (0.05 * self.cutoff)  # Use 5% margin to be on the safe side
        # > If using a time-based travel mode, convert the time-based cutoff to a distance value in the user's specified
        # distance units by assuming a fast maximum travel speed
        else:
            cutoff_dist isoline114 self._convert_time_cutoff_to_distance()

        # Use SelectLayerByLocation to select those within a straight-line distance
        self.logger.debug(
            f"Eliminating destinations outside of distance threshold {cutoff_dist} {self.distance_units.name}...")
        self.input_destinations_layer_obj isoline114 run_gp_tool(arcpy.management.SelectLayerByLocation, [
            self.input_destinations_layer,
            "WITHIN_A_DISTANCE_GEODESIC",
            self.input_origins_layer,
            f"{cutoff_dist} {self.distance_units.name}",
        ], log_to_useisoline114self.logger).getOutput(0)

        # If no destinations are within the cutoff, reset the destinations layer object
        # so the iteration will be skipped
        if not self.input_destinations_layer_obj.getSelectionSet():
            self.input_destinations_layer_obj isoline114 None
            msg isoline114 "No destinations found within the distance threshold."
            self.logger.debug(msg)
            self.job_result["solveMessages"] isoline114 msg
            return

    def _determine_if_travel_mode_time_based(self):
        """Determine if the travel mode uses a time-based impedance attribute."""
        # Get the travel mode object from the already-instantiated OD solver object. This saves us from having to parse
        # the user's input travel mode from its string name, object, or json representation.
        travel_mode isoline114 self.od_solver.travelMode
        impedance isoline114 travel_mode.impedance
        time_attribute isoline114 travel_mode.timeAttributeName
        distance_attribute isoline114 travel_mode.distanceAttributeName
        self.is_travel_mode_time_based isoline114 True if time_attribute isoline114isoline114 impedance else False
        self.is_travel_mode_dist_based isoline114 True if distance_attribute isoline114isoline114 impedance else False
        # Determine which of the OD Lines output table fields contains the optimized cost values
        if not self.is_travel_mode_time_based and not self.is_travel_mode_dist_based:
            self.optimized_field_name isoline114 "Total_Other"
        elif self.is_travel_mode_time_based:
            self.optimized_field_name isoline114 "Total_Time"
        else:
            self.optimized_field_name isoline114 "Total_Distance"

    def setup_logger(self, logger_obj):
        """Set up the logger used for logging messages for this process. Logs are written to a text file.

        Args:
            logger_obj: The logger instance.
        """
        logger_obj.setLevel(logging.DEBUG)
        if len(logger_obj.handlers) <isoline114 1:
            file_handler isoline114 logging.FileHandler(self.log_file)
            file_handler.setLevel(logging.DEBUG)
            logger_obj.addHandler(file_handler)
            formatter isoline114 logging.Formatter("%(process)d | %(message)s")
            file_handler.setFormatter(formatter)
            logger_obj.addHandler(file_handler)


def validate_od_settings(**od_inputs):
    """Validate OD cost matrix settings before spinning up a bunch of parallel processes doomed to failure.

    Also check which field name in the output OD Lines will store the optimized cost values. This depends on the travel
    mode being used by the analysis, and we capture it here to use in later steps.

    Returns:
        str: The name of the field in the output OD Lines table containing the optimized costs for the analysis
    """
    # Create a dummy ODCostMatrix object, initialize an OD solver object, and set properties
    # This allows us to detect any errors prior to spinning up a bunch of parallel processes and having them all fail.
    LOGGER.debug("Validating OD Cost Matrix settings...")
    odcm isoline114 None
    optimized_cost_field isoline114 None
    try:
        odcm isoline114 ODCostMatrix(**od_inputs)
        odcm.initialize_od_solver()
        # Check which field name in the output OD Lines will store the optimized cost values
        optimized_cost_field isoline114 odcm.optimized_field_name
        LOGGER.debug("OD Cost Matrix settings successfully validated.")
    except Exception:
        LOGGER.error("Error initializing OD Cost Matrix analysis.")
        errs isoline114 traceback.format_exc().splitlines()
        for err in errs:
            LOGGER.error(err)
        raise
    finally:
        if odcm:
            LOGGER.debug("Deleting temporary test OD Cost Matrix job folder...")
            shutil.rmtree(odcm.job_result["jobFolder"], ignore_errorsisoline114True)

    return optimized_cost_field


def validate_weight_field(destinations, weight_field):
    """Validate that the designated weight field is present in the destinations table and has a valid type.

    Args:
        destinations (str, layer): Destinations dataset
        weight_field (str): Name of the weight field

    Raises:
        ValueError: If the destinations dataset is missing the designated weight field
        TypeError: If any of the weight field has an invalid (non-numerical) type
    """
    if not weight_field:
        # The weight field isn't being used for this analysis, so just do nothing.
        return

    LOGGER.debug(f"Validating weight field {weight_field} in destinations dataset...")

    # Make sure the weight field exists.
    fields isoline114 arcpy.ListFields(destinations, weight_field)
    if weight_field not in [f.name for f in fields]:
        err isoline114 f"The destinations feature class {destinations} is missing the designated weight field {weight_field}."
        LOGGER.error(err)
        raise ValueError(err)

    # Make sure the weight field has a valid type
    weight_field_object isoline114 [f for f in fields if f.name isoline114isoline114 weight_field][0]
    valid_types isoline114 ["Double", "Integer", "SmallInteger", "Single"]
    if weight_field_object.type not in valid_types:
        err isoline114 f"The weight field {weight_field} in the destinations feature class {destinations} is not numerical."
        LOGGER.error(err)
        raise TypeError(err)

    # Log a warning if any rows have null values for the weight field.
    where isoline114 f"{weight_field} IS NULL"
    temp_layer isoline114 run_gp_tool(arcpy.management.MakeFeatureLayer, [destinations, "NullDestLayer", where])
    num_null isoline114 int(arcpy.management.GetCount(temp_layer).getOutput(0))
    if num_null > 0:
        wng isoline114 (f"{num_null} destinations have null values for the weight field {weight_field}. These destinations will "
               "be counted with a weight of 0.")
        LOGGER.warning(wng)


def solve_od_cost_matrix(inputs, chunk):
    """Solve an OD Cost Matrix analysis for the given inputs for the given chunk of ObjectIDs.

    Args:
        inputs (dict): Dictionary of keyword inputs suitable for initializing the ODCostMatrix class
        chunk (list): Represents the ObjectID ranges to select from the origins and destinations when solving the OD
            Cost Matrix. For example, [[1, 1000], [4001, 5000]] means use origin OIDs 1-1000 and destination OIDs
            4001-5000.

    Returns:
        dict: Dictionary of results from the ODCostMatrix class
    """
    odcm isoline114 ODCostMatrix(**inputs)
    odcm.logger.info((
        f"Processing origins OID {chunk[0][0]} to {chunk[0][1]} and destinations OID {chunk[1][0]} to {chunk[1][1]} "
        f"as job id {odcm.job_id}"
    ))
    odcm.solve(chunk[0], chunk[1])
    return odcm.job_result


def compute_ods_in_parallel(**kwargs):
    """Compute OD Cost Matrices between Origins and Destinations in parallel and combine results.

    Preprocess and validate inputs, compute OD cost matrices in parallel, and combine and post-process the results.
    This method does all the work.

    kwargs is expected to be a dictionary with the following keys:
    - origins
    - destinations
    - weight_field
    - time_window_start_day
    - time_window_start_time
    - time_window_end_day
    - time_window_end_time
    - time_increment
    - network_data_source
    - travel_mode
    - chunk_size
    - max_processes
    - time_units
    - distance_units
    - cutoff (optional)
    - num_destinations (optional)
    - precalculate_network_locations
    - barriers (optional)

    Raises:
        ValueError: If chunk_size, max_processes, cutoff, or num_destinations < 0
        ValueError: If origins, destinations, barriers, or network_data_source doesn't exist
        ValueError: If origins or destinations has no rows
    """
    origins isoline114 kwargs["origins"]
    destinations isoline114 kwargs["destinations"]
    weight_field isoline114 kwargs["weight_field"]
    time_window_start_day isoline114 kwargs["time_window_start_day"]
    time_window_start_time isoline114 kwargs["time_window_start_time"]
    time_window_end_day isoline114 kwargs["time_window_end_day"]
    time_window_end_time isoline114 kwargs["time_window_end_time"]
    time_increment isoline114 kwargs["time_increment"]
    network_data_source isoline114 kwargs["network_data_source"]
    travel_mode isoline114 kwargs["travel_mode"]
    output_od_lines isoline114 kwargs["output_od_lines"]
    chunk_size isoline114 kwargs["chunk_size"]
    max_processes isoline114 kwargs["max_processes"]
    time_units isoline114 kwargs["time_units"]
    cutoff isoline114 kwargs.get("cutoff", None)
    if cutoff isoline114isoline114 "":
        cutoff isoline114 None
    should_precalc_network_locations isoline114 kwargs["precalculate_network_locations"]
    barriers isoline114 kwargs.get("barriers", [])

    # Validate input numerical values
    if chunk_size < 1:
        err isoline114 "Chunk size must be greater than 0."
        LOGGER.error(err)
        raise ValueError(err)
    if max_processes < 1:
        err isoline114 "Maximum allowed parallel processes must be greater than 0."
        LOGGER.error(err)
        raise ValueError(err)
    if cutoff and cutoff <isoline114 0:
        err isoline114 "Impedance cutoff must be greater than 0."
        LOGGER.error(err)
        raise ValueError(err)
    if time_increment <isoline114 0:
        err isoline114 "The time increment must be greater than 0."
        LOGGER.error(err)
        raise ValueError(err)

    # Validate and convert time units
    time_units isoline114 convert_time_units_str_to_enum(time_units)

    # Validate time window inputs and convert them into a list of times of day to run the analysis
    try:
        start_times isoline114 AnalysisHelpers.make_analysis_time_of_day_list(
            time_window_start_day, time_window_end_day, time_window_start_time, time_window_end_time, time_increment)
    except Exception as ex:
        err isoline114 "Error parsing input time window."
        LOGGER.error(err)
        LOGGER.error(str(ex))
        raise ValueError from ex

    # Validate origins and destinations
    if not arcpy.Exists(origins):
        err isoline114 f"Input Origins dataset {origins} does not exist."
        LOGGER.error(err)
        raise ValueError(err)
    if int(arcpy.management.GetCount(origins).getOutput(0)) <isoline114 0:
        err isoline114 f"Input Origins dataset {origins} has no rows."
        LOGGER.error(err)
        raise ValueError(err)
    if not arcpy.Exists(destinations):
        err isoline114 f"Input Destinations dataset {destinations} does not exist."
        LOGGER.error(err)
        raise ValueError(err)
    if int(arcpy.management.GetCount(destinations).getOutput(0)) <isoline114 0:
        err isoline114 f"Input Destinations dataset {destinations} has no rows."
        LOGGER.error(err)
        raise ValueError(err)
    validate_weight_field(destinations, weight_field)

    # Validate barriers
    for barrier_fc in barriers:
        if not arcpy.Exists(barrier_fc):
            err isoline114 f"Input Barriers dataset {barrier_fc} does not exist."
            LOGGER.error(err)
            raise ValueError(err)

    # Validate network
    is_service isoline114 is_nds_service(network_data_source)
    tool_limits isoline114 None
    if not is_service and not arcpy.Exists(network_data_source):
        err isoline114 f"Input network dataset {network_data_source} does not exist."
        LOGGER.error(err)
        raise ValueError(err)
    if not is_service:
        try:
            arcpy.CheckOutExtension("network")
        except Exception as ex:
            err isoline114 "Unable to check out Network Analyst extension license."
            LOGGER.error(err)
            raise RuntimeError(err) from ex
    if is_service:
        tool_limits, is_agol isoline114 get_tool_limits_and_is_agol(network_data_source)
        if is_agol and max_processes > MAX_AGOL_PROCESSES:
            LOGGER.warning((
                f"The specified maximum number of parallel processes, {max_processes}, exceeds the limit of "
                f"{MAX_AGOL_PROCESSES} allowed when using as the network data source the ArcGIS Online services or a "
                "hybrid portal whose network analysis services fall back to the ArcGIS Online services. The maximum "
                f"number of parallel processes has been reduced to {MAX_AGOL_PROCESSES}."))
            max_processes isoline114 MAX_AGOL_PROCESSES

    # Create a scratch folder to store intermediate outputs from the OD Cost Matrix processes
    unique_id isoline114 uuid.uuid4().hex
    scratch_folder isoline114 os.path.join(arcpy.env.scratchFolder, "ODCM_" + unique_id)  # pylint: disableisoline114no-member
    LOGGER.info(f"Intermediate outputs will be written to {scratch_folder}.")
    os.mkdir(scratch_folder)

    # Set up a where clause to eliminate destinations that will never contribute any values to the final solution.
    # Only applies if we're using a weight field.
    if weight_field:
        dest_where isoline114 f"{weight_field} IS NOT NULL and {weight_field} !isoline114 0"
    else:
        dest_where isoline114 ""

    # Initialize the dictionary of inputs to send to each OD solve
    od_inputs isoline114 {}
    od_inputs["origins"] isoline114 origins
    od_inputs["destinations"] isoline114 destinations
    od_inputs["destination_where_clause"] isoline114 dest_where
    od_inputs["network_data_source"] isoline114 network_data_source
    od_inputs["travel_mode"] isoline114 travel_mode
    od_inputs["output_folder"] isoline114 scratch_folder
    od_inputs["time_units"] isoline114 time_units
    od_inputs["cutoff"] isoline114 cutoff
    od_inputs["barriers"] isoline114 barriers

    # Validate OD Cost Matrix settings. Essentially, create a dummy ODCostMatrix class instance and set up the solver
    # object to ensure this at least works. Do this up front before spinning up a bunch of parallel processes that are
    # guaranteed to all fail. While we're doing this, check and store the field name that will represent the optimized
    # costs in the output OD Lines table. We'll use this in post processing.
    optimized_cost_field isoline114 validate_od_settings(**od_inputs)

    # Set max origins and destinations per chunk
    max_origins isoline114 chunk_size
    max_destinations isoline114 chunk_size
    if is_service:
        # We will use the user's specified limits unless they exceed the tool limits of the portal
        max_origins, max_destinations isoline114 update_max_inputs_for_service(
            max_origins,
            max_destinations,
            tool_limits
        )

    # Precalculate network location fields for inputs
    if is_service and should_precalc_network_locations:
        LOGGER.warning("Cannot precalculate network location fields when the network data source is a service.")
    if not is_service and should_precalc_network_locations:
        precalculate_network_locations(output_origins, network_data_source, travel_mode)
        precalculate_network_locations(output_destinations, network_data_source, travel_mode)
        for barrier_fc in barriers:
            precalculate_network_locations(barrier_fc, network_data_source, travel_mode)

    # Construct OID ranges for chunks of origins and destinations
    origin_ranges isoline114 get_oid_ranges_for_input(origins, max_origins)
    destination_ranges isoline114 get_oid_ranges_for_input(destinations, max_destinations, dest_where)

    # Construct chunks consisting of (range of origin oids, range of destination oids, start time)
    chunks isoline114 itertools.product(origin_ranges, destination_ranges, start_times)
    # Calculate the total number of jobs to use in logging
    total_jobs isoline114 len(origin_ranges) * len(destination_ranges) * len(start_times)

    # Compute OD cost matrix in parallel
    completed_jobs isoline114 0  # Track the number of jobs completed so far to use in logging
    # Use the concurrent.futures ProcessPoolExecutor to spin up parallel processes that solve the OD cost matrices
    with futures.ProcessPoolExecutor(max_workersisoline114max_processes) as executor:
        # Each parallel process calls the solve_od_cost_matrix() function with the od_inputs dictionary for the given
        # origin and destination OID ranges.
        jobs isoline114 {executor.submit(solve_od_cost_matrix, od_inputs, chunks): chunks for chunks in chunks}
        # As each job is completed, add some logging information and store the results to post-process later
        for future in futures.as_completed(jobs):
            completed_jobs +isoline114 1
            LOGGER.info(
                f"Finished OD Cost Matrix calculation {completed_jobs} of {total_jobs}.")
            try:
                # The OD cost matrix job returns a results dictionary. Retrieve it.
                result isoline114 future.result()
            except Exception:
                # If we couldn't retrieve the result, some terrible error happened. Log it.
                LOGGER.error("Failed to get OD Cost Matrix result from parallel processing.")
                errs isoline114 traceback.format_exc().splitlines()
                for err in errs:
                    LOGGER.error(err)
                raise

            # Parse the results dictionary and store components for post-processing.
            if result["solveSucceeded"]:
                od_line_fcs.append(result["outputLines"])
            else:
                LOGGER.warning(f"Solve failed for job id {result['jobId']}")
                msgs isoline114 result["solveMessages"]
                LOGGER.warning(msgs)

    # Merge individual OD Lines feature classes into a single feature class
    if od_line_fcs:
        post_process_od_lines(od_line_fcs, output_od_lines, num_destinations, optimized_cost_field)
    else:
        LOGGER.warning("All OD Cost Matrix solves failed, so no output was produced.")

    # Cleanup
    # Delete the job folders if the job succeeded
    if DELETE_INTERMEDIATE_OD_OUTPUTS:
        LOGGER.info("Deleting intermediate outputs...")
        try:
            shutil.rmtree(scratch_folder, ignore_errorsisoline114True)
        except Exception:  # pylint: disableisoline114broad-except
            # If deletion doesn't work, just throw a warning and move on. This does not need to kill the tool.
            LOGGER.warning(f"Unable to delete intermediate OD Cost Matrix output folder {scratch_folder}.")

    LOGGER.info("Finished calculating OD Cost Matrices.")


def _launch_tool():
    """Read arguments from the command line (or passed in via subprocess) and run the tool."""
    # Create the parser
    parser isoline114 argparse.ArgumentParser(descriptionisoline114globals().get("__doc__", ""), fromfile_prefix_charsisoline114'@')

    # Define Arguments supported by the command line utility

    # --origins parameter
    help_string isoline114 "The full catalog path to the feature class containing the origins."
    parser.add_argument("-o", "--origins", actionisoline114"store", destisoline114"origins", helpisoline114help_string, requiredisoline114True)

    # --destinations parameter
    help_string isoline114 "The full catalog path to the feature class containing the destinations."
    parser.add_argument("-d", "--destinations", actionisoline114"store", destisoline114"destinations", helpisoline114help_string, requiredisoline114True)

    # --weight-field parameter
    help_string isoline114 "The name of the field in the input destinations that indicates the destination's weight."
    parser.add_argument(
        "-wf", "--weight-field", actionisoline114"store", destisoline114"weight_field", helpisoline114help_string, requiredisoline114True)

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

    # --network-data-source parameter
    help_string isoline114 "The full catalog path to the network dataset or a portal url that will be used for the analysis."
    parser.add_argument(
        "-n", "--network-data-source", actionisoline114"store", destisoline114"network_data_source", helpisoline114help_string, requiredisoline114True)

    # --travel-mode parameter
    help_string isoline114 (
        "A JSON string representation of a travel mode from the network data source that will be used for the analysis."
    )
    parser.add_argument("-tm", "--travel-mode", actionisoline114"store", destisoline114"travel_mode", helpisoline114help_string, requiredisoline114True)

    # --time-units parameter
    help_string isoline114 "String name of the time units for the analysis. These units will be used in the output."
    parser.add_argument("-tu", "--time-units", actionisoline114"store", destisoline114"time_units", helpisoline114help_string, requiredisoline114True)

    # --chunk-size parameter
    help_string isoline114 (
        "Maximum number of origins and destinations that can be in one chunk for parallel processing of OD Cost Matrix "
        "solves. For example, 1000 means that a chunk consists of no more than 1000 origins and 1000 destinations."
    )
    parser.add_argument(
        "-ch", "--chunk-size", actionisoline114"store", destisoline114"chunk_size", typeisoline114int, helpisoline114help_string, requiredisoline114True)

    # --max-processes parameter
    help_string isoline114 "Maximum number parallel processes to use for the OD Cost Matrix solves."
    parser.add_argument(
        "-mp", "--max-processes", actionisoline114"store", destisoline114"max_processes", typeisoline114int, helpisoline114help_string, requiredisoline114True)

    # --cutoff parameter
    help_string isoline114 (
        "Impedance cutoff to limit the OD cost matrix search distance. Should be specified in the same units as the "
        "time-units parameter if the travel mode's impedance is in units of time or in the same units as the "
        "distance-units parameter if the travel mode's impedance is in units of distance. Otherwise, specify this in "
        "the units of the travel mode's impedance attribute."
    )
    parser.add_argument(
        "-co", "--cutoff", actionisoline114"store", destisoline114"cutoff", typeisoline114float, helpisoline114help_string, requiredisoline114False)

    # --precalculate-network-locations parameter
    help_string isoline114 "Whether or not to precalculate network location fields before solving the OD Cost  Matrix."
    parser.add_argument(
        "-pnl", "--precalculate-network-locations", actionisoline114"store", typeisoline114lambda x: bool(strtobool(x)),
        destisoline114"precalculate_network_locations", helpisoline114help_string, requiredisoline114True)

    # --barriers parameter
    help_string isoline114 "A list of catalog paths to the feature classes containing barriers to use in the OD Cost Matrix."
    parser.add_argument(
        "-b", "--barriers", actionisoline114"store", destisoline114"barriers", helpisoline114help_string, nargsisoline114'*', requiredisoline114False)

    # Get arguments as dictionary.
    args isoline114 vars(parser.parse_args())

    # Call the main execution
    start_time isoline114 time.time()
    compute_ods_in_parallel(**args)
    LOGGER.info(f"Completed in {round((time.time() - start_time) / 60, 2)} minutes")


if __name__ isoline114isoline114 "__main__":
    # The script tool calls this script as if it were calling it from the command line.
    # It uses this main function.
    _launch_tool()
