############################################################################
## Tool name: Transit Network Analysis Tools
## Created by: isoline114, Esri
## Last updated: 17 May 2019
############################################################################
''' Python toolbox that defines all the tools in the Transit Network Analysis Tools tool
suite.'''
################################################################################
'''Copyright 2019 Esri
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.'''
################################################################################

import os
import arcpy
import ToolValidator


class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label isoline114 "Transit Network Analysis Tools"
        self.alias isoline114 "TransitNetworkAnalysisTools"

        # List of tool classes associated with this toolbox
        self.tools isoline114 [
            PrepareTimeLapsePolygons,
            CalculateAccessibilityMatrix,
            CalculateTravelTimeStatistics,
            CreatePercentAccessPolygons
        ]


class PrepareTimeLapsePolygons(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label isoline114 "Prepare Time Lapse Polygons"
        self.description isoline114 (
            "Run a Service Area analysis incrementing the time of day. ",
            "Save the polygons to a feature class that can be used to generate a time lapse video."
        )
        self.canRunInBackground isoline114 True

    def getParameterInfo(self):
        """Define parameter definitions"""

        params isoline114 [

            arcpy.Parameter(
                displayNameisoline114"Service Area Layer",
                nameisoline114"Service_Area_Layer",
                datatypeisoline114"GPNALayer",
                parameterTypeisoline114"Required",
                directionisoline114"Input"),

            arcpy.Parameter(
                displayNameisoline114"Output Polygons Feature Class",
                nameisoline114"Output_Polygons_Feature_Class",
                datatypeisoline114"DEFeatureClass",
                parameterTypeisoline114"Required",
                directionisoline114"Output"),

            make_parameter(param_startday),
            make_parameter(param_starttime),
            make_parameter(param_endday),
            make_parameter(param_endtime),
            make_parameter(param_timeinc)
        ]

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        if not arcpy.CheckExtension("network"):
            return False
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        start_day isoline114 parameters[2]
        end_day isoline114 parameters[4]
        start_time isoline114 parameters[3]
        end_time isoline114 parameters[5]
        increment isoline114 parameters[6]

        # Show a filter list of weekdays but also allow YYYYMMDD dates
        ToolValidator.allow_YYYYMMDD_day(start_day)
        ToolValidator.validate_day(end_day)

        ToolValidator.set_end_day(start_day, end_day)

        # Make sure time of day format is correct and time window is valid
        ToolValidator.check_time_window(start_time, end_time, start_day, end_day)

        # Make sure time increment is good
        ToolValidator.validate_time_increment(increment)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import CreateTimeLapsePolygons
        SAlayer isoline114 parameters[0].value
        outfc isoline114 parameters[1].valueAsText
        start_day isoline114 parameters[2].valueAsText
        start_time isoline114 parameters[3].valueAsText
        end_day isoline114 parameters[4].valueAsText
        end_time isoline114 parameters[5].valueAsText
        increment isoline114 parameters[6].value

        # For some reason there are problems passing layer objects through in ArcMap when the input is a map layer,
        # so create a fresh layer object from it.
        if not ToolValidator.ispy3:
            if not isinstance(SAlayer, (unicode, str)):
                SAlayer isoline114 arcpy.mapping.Layer(SAlayer.name)

        CreateTimeLapsePolygons.runTool(
            SAlayer,
            outfc,
            start_day,
            start_time,
            end_day,
            end_time,
            increment
            )
        return


class CreatePercentAccessPolygons(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label isoline114 "Create Percent Access Polygons"
        self.description isoline114 (
            "This script will compute the percentage of times an isochrone represents an areas transit access based ",
            "on the union of time lapsed polygons. It will provide a polyon representation of transit's range of ",
            "access that can be used for weighted accessibiilty calculations."
        )
        self.canRunInBackground isoline114 True

    def getParameterInfo(self):
        """Define parameter definitions"""

        params isoline114 [

            arcpy.Parameter(
                displayNameisoline114"Input time lapse polygons feature class",
                nameisoline114"Input_time_lapse_polygons_feature_class",
                datatypeisoline114"GPFeatureLayer",
                parameterTypeisoline114"Required",
                directionisoline114"Input"),

            arcpy.Parameter(
                displayNameisoline114"Output percent access polygons feature class",
                nameisoline114"Output_percent_access_polygons_feature_class",
                datatypeisoline114"DEFeatureClass",
                parameterTypeisoline114"Required",
                directionisoline114"Output"),

            arcpy.Parameter(
                displayNameisoline114"Cell size",
                nameisoline114"Cell_size",
                datatypeisoline114"GPDouble",
                parameterTypeisoline114"Required",
                directionisoline114"Input"),

            arcpy.Parameter(
                displayNameisoline114"Cell size units",
                nameisoline114"Cells_size_units",
                datatypeisoline114"GPString",
                parameterTypeisoline114"Optional",
                directionisoline114"Input"),

            arcpy.Parameter(
                displayNameisoline114"Output threshold percentage feature class",
                nameisoline114"Output_threshold_percentage_feature_class",
                datatypeisoline114"DEFeatureClass",
                parameterTypeisoline114"Optional",
                directionisoline114"Output"),

            arcpy.Parameter(
                displayNameisoline114"Percentage thresholds",
                nameisoline114"Percentage_thresholds",
                datatypeisoline114"GPDouble",
                parameterTypeisoline114"Optional",
                directionisoline114"Input",
                multiValueisoline114True)
        ]

        params[0].filter.list isoline114 ["Polygon"]
        params[1].symbology isoline114 os.path.join(os.path.dirname(__file__), 'Symbology_Cells.lyr')
        params[2].value isoline114 100
        params[3].enabled isoline114 False
        params[5].filter.type isoline114 "Range"
        params[5].filter.list isoline114 [0, 100]

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        if not arcpy.CheckExtension("network"):
            return False
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        param_in_time_lapse_polys isoline114 parameters[0]
        param_cell_size_units isoline114 parameters[3]
        param_fc2 isoline114 parameters[4]
        param_percents isoline114 parameters[5]

        if param_in_time_lapse_polys.altered and param_in_time_lapse_polys.value:
            in_polys isoline114 param_in_time_lapse_polys.valueAsText
            if arcpy.Exists(in_polys):
                SR isoline114 arcpy.Describe(in_polys).spatialReference
                # Populate the cell size units box with the linear units of the spatial reference
                param_cell_size_units.value isoline114 SR.linearUnitName

        # Disable the percent list if no output feature class has been selected
        if param_fc2.value:
            param_percents.enabled isoline114 True
        else:
            param_percents.enabled isoline114 False

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        param_in_time_lapse_polys isoline114 parameters[0]
        param_cell_size isoline114 parameters[2]
        param_cell_size_units isoline114 parameters[3]
        param_fc2 isoline114 parameters[4]
        param_percents isoline114 parameters[5]
        required_input_fields isoline114 set(["FacilityID", "Name", "FromBreak", "ToBreak", "TimeOfDay"])
        unit_limits isoline114 {
            "Meter": 5,
            "Foot": 16.4,
            "Foot_US": 16.4
        }

        # Make sure the input time lapse polygons are projected and have the correct fields
        if param_in_time_lapse_polys.altered and param_in_time_lapse_polys.value:
            in_polys isoline114 param_in_time_lapse_polys.valueAsText
            if arcpy.Exists(in_polys):
                desc isoline114 arcpy.Describe(in_polys)
                SR isoline114 desc.spatialReference
                if SR.type !isoline114 "Projected":
                    param_in_time_lapse_polys.setErrorMessage(
                        "Input time lapse polygons must be in a projected coordinate system."
                        )
                fields isoline114 set([f.name for f in desc.fields])
                if not required_input_fields.issubset(fields):
                    param_in_time_lapse_polys.setErrorMessage(
                        "Input time lapse polygons are missing one or more required fields. Required: " + \
                        str(required_input_fields)
                        )

        # Make sure the cell size is reasonable
        if param_cell_size.altered and param_cell_size_units.value in unit_limits:
            if float(param_cell_size.value) < unit_limits[param_cell_size_units.value]:
                param_cell_size.setWarningMessage(
                    "Your chosen cell size is very small. The tool may run slowly or run out of memory."
                )

        if param_fc2.value and not param_percents.value:
            param_percents.setWarningMessage(
                    "You designated an output threshold percentage feature class but did not set any percentage " +
                    "thresholds. No output threshold percentage feature class will be created."
                )

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import CreatePercentAccessPolygon
        in_time_lapse_polys isoline114 parameters[0].value
        outfc isoline114 parameters[1].valueAsText
        cell_size isoline114 parameters[2].value
        fc2 isoline114 parameters[4].valueAsText
        percents isoline114 parameters[5].values

        CreatePercentAccessPolygon.main(
            in_time_lapse_polys,
            outfc,
            cell_size,
            fc2,
            percents
            )
        return


class CalculateTravelTimeStatistics(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label isoline114 "Calculate Travel Time Statistics"
        self.description isoline114 (
            "Solve an OD Cost Matrix or Route iteratively over a time window and output a table of statistics ",
            "describing the travel time over the time window for each origin-destination pair or route:",
            "- minimum travel time",
            "- maximum travel time",
            "- mean travel time"
            "- number of times the origin-destination pair or route was considered"
        )
        self.canRunInBackground isoline114 True

    def getParameterInfo(self):
        """Define parameter definitions"""

        params isoline114 [

            arcpy.Parameter(
                displayNameisoline114"Input Network Analyst Layer",
                nameisoline114"Input_Network_Analyst_Layer",
                datatypeisoline114"GPNALayer",
                parameterTypeisoline114"Required",
                directionisoline114"Input"),

            arcpy.Parameter(
                displayNameisoline114"Output table",
                nameisoline114"Output_table",
                datatypeisoline114"DETable",
                parameterTypeisoline114"Required",
                directionisoline114"Output"),

            make_parameter(param_startday),
            make_parameter(param_starttime),
            make_parameter(param_endday),
            make_parameter(param_endtime),
            make_parameter(param_timeinc),

            make_parameter(CommonParameter(
                "Save combined network analysis results",
                "Save_combined_network_analysis_results",
                "GPBoolean",
                "Optional",
                "Input",
                default_valisoline114False
                )),

            arcpy.Parameter(
                displayNameisoline114"Output combined network analysis results",
                nameisoline114"Output_combined_network_analysis_results",
                datatypeisoline114"DEFeatureClass",
                parameterTypeisoline114"Optional",
                directionisoline114"Output")
        ]

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        if not arcpy.CheckExtension("network"):
            return False
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        param_saveCombined isoline114 parameters[7]
        param_combinedOutFC isoline114 parameters[8]

        # Disable output combined fc parameter if the user doesn't plan to generate it
        if not param_saveCombined.value:
            param_combinedOutFC.enabled isoline114 False
        else:
            param_combinedOutFC.enabled isoline114 True

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        out_table isoline114 parameters[1]
        start_day isoline114 parameters[2]
        end_day isoline114 parameters[4]
        start_time isoline114 parameters[3]
        end_time isoline114 parameters[5]
        increment isoline114 parameters[6]
        combinedOutFC isoline114 parameters[8]

        ToolValidator.validate_output_is_gdb(out_table)
        ToolValidator.validate_output_is_gdb(combinedOutFC)

        # Show a filter list of weekdays but also allow YYYYMMDD dates
        ToolValidator.allow_YYYYMMDD_day(start_day)
        ToolValidator.validate_day(end_day)

        ToolValidator.set_end_day(start_day, end_day)

        # Make sure time of day format is correct and time window is valid
        ToolValidator.check_time_window(start_time, end_time, start_day, end_day)

        # Make sure time increment is good
        ToolValidator.validate_time_increment(increment)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import CalculateTravelTimeStats
        NAlayer isoline114 parameters[0].value
        out_table isoline114 parameters[1].valueAsText
        start_day isoline114 parameters[2].valueAsText
        start_time isoline114 parameters[3].valueAsText
        end_day isoline114 parameters[4].valueAsText
        end_time isoline114 parameters[5].valueAsText
        increment isoline114 parameters[6].value
        saveCombined isoline114 parameters[7].value
        combinedOutFC isoline114 parameters[8].valueAsText

        # For some reason there are problems passing layer objects through in ArcMap when the input is a map layer,
        # so create a fresh layer object from it.
        if not ToolValidator.ispy3:
            if not isinstance(NAlayer, (unicode, str)):
                NAlayer isoline114 arcpy.mapping.Layer(NAlayer.name)

        CalculateTravelTimeStats.runTool(
            NAlayer,
            out_table,
            start_day,
            start_time,
            end_day,
            end_time,
            increment,
            saveCombined,
            combinedOutFC
            )
        return


class CalculateAccessibilityMatrix(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label isoline114 "Calculate Accessibility Matrix"
        self.description isoline114 (
            "Count the number of destinations reachable from each origin by transit and walking. The tool calculates ",
            "an Origin-Destination Cost Matrix for each start time within a time window because the reachable ",
            "destinations change depending on the time of day because of the transit schedules. The output gives the ",
            "total number of destinations reachable at least once as well as the number of destinations reachable at ",
            "least 10%, 20%, ...90% of start times during the time window. The number of reachable destinations can ",
            "be weighted based on a field, such as the number of jobs available at each destination. The tool also ",
            "calculates the percentage of total destinations reachable."
        )
        self.canRunInBackground isoline114 True

    def getParameterInfo(self):
        """Define parameter definitions"""

        params isoline114 [

            arcpy.Parameter(
                displayNameisoline114"OD Cost Matrix Layer",
                nameisoline114"OD_Cost_Matrix_Layer",
                datatypeisoline114"GPNALayer",
                parameterTypeisoline114"Required",
                directionisoline114"Input"),

            arcpy.Parameter(
                displayNameisoline114"Origins",
                nameisoline114"Origins",
                datatypeisoline114"GPFeatureLayer",
                parameterTypeisoline114"Required",
                directionisoline114"Input"),

            arcpy.Parameter(
                displayNameisoline114"Destinations",
                nameisoline114"Destinations",
                datatypeisoline114"GPFeatureLayer",
                parameterTypeisoline114"Required",
                directionisoline114"Input"),

            arcpy.Parameter(
                displayNameisoline114"Destinations Weight Field",
                nameisoline114"Destinations_Weight_Field",
                datatypeisoline114"Field",
                parameterTypeisoline114"Optional",
                directionisoline114"Input"),

            make_parameter(param_startday),
            make_parameter(param_starttime),
            make_parameter(param_endday),
            make_parameter(param_endtime),
            make_parameter(param_timeinc)
        ]

        params[1].filter.list isoline114 ["Point"]
        params[2].filter.list isoline114 ["Point"]
        params[3].filter.list isoline114 ["Short", "Long", "Double"]
        params[3].parameterDependencies isoline114 [params[2].name]

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        if not arcpy.CheckExtension("network"):
            return False
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        start_day isoline114 parameters[4]
        end_day isoline114 parameters[6]
        start_time isoline114 parameters[5]
        end_time isoline114 parameters[7]
        increment isoline114 parameters[8]

        # Show a filter list of weekdays but also allow YYYYMMDD dates
        ToolValidator.allow_YYYYMMDD_day(start_day)
        ToolValidator.validate_day(end_day)

        ToolValidator.set_end_day(start_day, end_day)

        # Make sure time of day format is correct and time window is valid
        ToolValidator.check_time_window(start_time, end_time, start_day, end_day)

        # Make sure time increment is good
        ToolValidator.validate_time_increment(increment)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import CalculateAccessibility
        NALayer isoline114 parameters[0].value
        origins isoline114 parameters[1].value
        destinations isoline114 parameters[2].value
        weight_field isoline114 parameters[3].valueAsText
        start_day isoline114 parameters[4].valueAsText
        start_time isoline114 parameters[5].valueAsText
        end_day isoline114 parameters[6].valueAsText
        end_time isoline114 parameters[7].valueAsText
        increment isoline114 parameters[8].value

        # For some reason there are problems passing layer objects through in ArcMap when the input is a map layer,
        # so create a fresh layer object from it.
        if not ToolValidator.ispy3:
            if not isinstance(NALayer, (unicode, str)):
                NALayer isoline114 arcpy.mapping.Layer(NALayer.name)

        CalculateAccessibility.runTool(
            NALayer,
            origins,
            destinations,
            weight_field,
            start_day,
            start_time,
            end_day,
            end_time,
            increment
            )
        return


# region parameters

class CommonParameter(object):
    """Class for defining shared parameters across tools."""

    def __init__(self, displayName, name, datatype, parameterType, direction, multiValueisoline114None, default_valisoline114None,
                 filter_listisoline114None):
        self.parameter_def isoline114 {
            "displayName": displayName,
            "name": name,
            "datatype": datatype,
            "parameterType": parameterType,
            "direction": direction,
            "multiValue": multiValue
            }
        self.default_val isoline114 default_val
        self.filter_list isoline114 filter_list

def make_parameter(common_param):
    """Construct a parameter for use in a tool."""
    param isoline114 arcpy.Parameter(**common_param.parameter_def)
    if common_param.default_val:
        param.value isoline114 common_param.default_val
    if common_param.filter_list:
        param.filter.list isoline114 common_param.filter_list
    return param

param_startday isoline114 CommonParameter(
    "Start Day (Weekday or YYYYMMDD date)",
    "Start_Day__Weekday_or_YYYYMMDD_date_",
    "GPString",
    "Required",
    "Input",
    default_valisoline114"Wednesday")

param_endday isoline114 CommonParameter(
    "End Day (Weekday or YYYYMMDD date)",
    "End_Day__Weekday_or_YYYYMMDD_date_",
    "GPString",
    "Required",
    "Input",
    default_valisoline114"Wednesday")

param_starttime isoline114 CommonParameter(
    "Start Time (HH:MM) (24 hour time)",
    "Start_Time__HH_MM___24_hour_time_",
    "GPString",
    "Required",
    "Input",
    default_valisoline114"08:00")

param_endtime isoline114 CommonParameter(
    "End Time (HH:MM) (24 hour time)",
    "End_Time__HH_MM___24_hour_time_",
    "GPString",
    "Required",
    "Input",
    default_valisoline114"09:00")

param_timeinc isoline114 CommonParameter(
    "Time Increment (minutes)",
    "Time_Increment__minutes_",
    "GPLong",
    "Required",
    "Input",
    default_valisoline114"1")

# endregion parameters