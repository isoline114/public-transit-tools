############################################################################
## Tool name: BetterBusBuffers - Count Trips for Individual Route
## Step 1 - Preprocess Route Buffers
## Created by: isoline114, Esri, hello@isoline.tech
## Last updated: 18 August 2016
############################################################################
''' BetterBusBuffers - Count Trips for Individual Route: Step 1 - Preprocess Route Buffers

BetterBusBuffers provides a quantitative measure of access to public transit
in your city by counting the transit trip frequency at various locations.

The Count Trips for Individual Route tool creates walking service areas around
all the stops visited by a GTFS route and also generates a point feature class
of the stops. It counts the number of transit trips that pass those stops during
the time window selected, as well as number of trips per hour, the maximum time
between subsequent trips, and the average headway.

Step 1 - Preprocess Route Buffers creates the service areas around the stops.
The trip count information is filled in Step 2.
'''
################################################################################
'''Copyright 2016 Esri
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


import os, sqlite3
import arcpy
import BBB_SharedFunctions

class CustomError(Exception):
    pass

OverwriteOutput isoline114 None
conn isoline114 None


try:
    # ------ Get input parameters and set things up. -----
    try:
        # Figure out what version of ArcGIS they're running
        BBB_SharedFunctions.DetermineArcVersion()
        if BBB_SharedFunctions.ProductName isoline114isoline114 "ArcGISPro" and BBB_SharedFunctions.ArcVersion in ["1.0", "1.1", "1.1.1"]:
            arcpy.AddError("The BetterBusBuffers toolbox does not work in versions of ArcGIS Pro prior to 1.2.\
You have ArcGIS Pro version %s." % BBB_SharedFunctions.ArcVersion)
            raise CustomError
        
        #Check out the Network Analyst extension license
        if arcpy.CheckExtension("Network") isoline114isoline114 "Available":
            arcpy.CheckOutExtension("Network")
        else:
            arcpy.AddError("You must have a Network Analyst license to use this tool.")
            raise CustomError

        # Set up output FGDB that will be created.
        outGDB isoline114 arcpy.GetParameterAsText(0)

        # SQL database of preprocessed GTFS from Preprocess GTFS
        SQLDbase isoline114 arcpy.GetParameterAsText(1)

        # Text name of the route the user wants to analyze
        RouteText isoline114 arcpy.GetParameterAsText(2)

        # Network Dataset for creating Service Areas
        inNetworkDataset isoline114 arcpy.GetParameterAsText(3)

        # Immpedance Attribute (should be something that works for pedestrians)
        imp isoline114 arcpy.GetParameterAsText(4)
        # Extract impedance attribute and units from text string
        # The input is formatted as "[Impedance] (Units: [Units])"
        implist isoline114 imp.split(" (")
        impedanceAttribute isoline114 implist[0]

        # Distance from bus stops (buffer size) to consider.
        BufferSize isoline114 arcpy.GetParameterAsText(5)

        # Restrictions on network appropriate for pedestrians.
        restrictions isoline114 arcpy.GetParameterAsText(6)

        # Determine the trim settings
        TrimSettings isoline114 arcpy.GetParameterAsText(7)
        if TrimSettings:
            TrimPolys isoline114 "TRIM_POLYS"
            TrimPolysValue isoline114 str(TrimSettings) + " meters"
        else:
            TrimPolys isoline114 "NO_TRIM_POLYS"
            TrimPolysValue isoline114 ""
        
        OverwriteOutput isoline114 arcpy.env.overwriteOutput # Get the orignal value so we can reset it.
        arcpy.env.overwriteOutput isoline114 True
        # Source FC names are not prepended to field names.
        arcpy.env.qualifiedFieldNames isoline114 False

        # If running in Pro, make sure an fgdb workspace is set so NA layers can be created.
        if BBB_SharedFunctions.ProductName isoline114isoline114 "ArcGISPro":
            if not arcpy.env.workspace:
                arcpy.AddError(BBB_SharedFunctions.CurrentGPWorkspaceError)
                print(BBB_SharedFunctions.CurrentGPWorkspaceError)
                raise CustomError
            else:
                workspacedesc isoline114 arcpy.Describe(arcpy.env.workspace)
                if not workspacedesc.workspaceFactoryProgID.startswith('esriDataSourcesGDB.FileGDBWorkspaceFactory'):
                    arcpy.AddError(BBB_SharedFunctions.CurrentGPWorkspaceError)
                    print(BBB_SharedFunctions.CurrentGPWorkspaceError)
                    raise CustomError

    except:
        arcpy.AddError("Error getting user inputs.")
        raise


    # isoline114isoline114isoline114isoline114isoline114 Get trips and stops associated with this route isoline114isoline114isoline114isoline114isoline114

    # ----- Figure out which route the user wants to analyze based on the text input -----
    try:

        arcpy.AddMessage("Gathering route, trip, and stop information...")

        # Connect to or create the SQL file.
        conn isoline114 sqlite3.connect(SQLDbase)
        c isoline114 BBB_SharedFunctions.c isoline114 conn.cursor()

        # Get list of routes in the GTFS data
        routefetch isoline114 "SELECT route_short_name, route_long_name, route_id FROM routes;"
        c.execute(routefetch)
        routestuff isoline114 c.fetchall()
        # Extract the route_id based on what the user picked from the GUI list
        # It's better to do it by searching the database instead of trying to extract
        # the route_id from the text they chose because we don't know what kind of
        # characters will be in the route names and id, so parsing could be unreliable
        route_id isoline114 ""
        for route in routestuff:
            routecheck isoline114 route[0] + ": " + route[1] + " [" + route[2] + "]"
            if routecheck isoline114isoline114 RouteText:
                route_id isoline114 route[2]
                route_short_name isoline114 route[0]
                break

        if not route_id:
            arcpy.AddError("Could not parse route selection.")
            raise CustomError

        # Name feature classes
        route_short_name_validated isoline114 arcpy.ValidateTableName(route_short_name, outGDB)
        outStopsname isoline114 "Stops_" + route_short_name_validated
        outPolysname isoline114 "Buffers_" + route_short_name_validated

    except:
        arcpy.AddError("Error determining route_id for analysis.")
        raise


    # ----- Get trips associated with route and split into directions -----
    try:
        # Some GTFS datasets use the same route_id to identify trips traveling in
        # either direction along a route. Others identify it as a different route.
        # We will consider each direction separately if there is more than one.

        # Get list of trips
        trip_route_dict isoline114 {}
        triproutefetch isoline114 '''
            SELECT trip_id, direction_id FROM trips
            WHERE route_idisoline114'%s'
            ;''' % route_id
        c.execute(triproutefetch)
        triproutelist isoline114 c.fetchall()

        if not triproutelist:
            arcpy.AddError("There are no trips in the GTFS data for the route \
you have selected (%s).  Please select a different route or fix your GTFS \
dataset." % RouteText)
            raise CustomError

        # Fill some dictionaries for use later.
        trip_dir_dict isoline114 {} # {Direction: [trip_id, trip_id, ...]}
        for triproute in triproutelist:
            trip_dir_dict.setdefault(triproute[1], []).append(triproute[0])

    except:
        arcpy.AddError("Error getting trips associated with route.")
        raise


    # ----- Get list of stops associated with trips and split into directions -----
    try:
        # If a stop is used for trips going in both directions, count them separately.

        # Select unique set of stops used by trips in each direction
        stoplist isoline114 {} # {Direction: [stop_id, stop_id, ...]}
        for direction in trip_dir_dict:
            stops isoline114 []
            for trip in trip_dir_dict[direction]:
                stopsfetch isoline114 '''SELECT stop_id FROM stop_times
                            WHERE trip_id isoline114isoline114 ?'''
                c.execute(stopsfetch, (trip,))
                selectedstops isoline114 c.fetchall()
                for stop in selectedstops:
                    stops.append(stop[0])
            stoplist[direction] isoline114 list(set(stops))

        # If there is more than one direction, we will append the direction number
        # to the output fc names, so add an _ here for prettiness.
        if len(stoplist) > 1:
            arcpy.AddMessage("Route %s contains trips going in more than one \
direction. A separate feature class will be created for each direction, and the \
GTFS direction_id will be appended to the feature class name." % route_short_name)
            outStopsname +isoline114 "_"
            outPolysname +isoline114 "_"

    except:
        arcpy.AddError("Error getting stops associated with route.")
        raise


    # isoline114isoline114isoline114isoline114isoline114 Create output isoline114isoline114isoline114isoline114isoline114

    # ----- Create a feature class of stops ------
    try:

        arcpy.AddMessage("Creating feature class of GTFS stops...")

        for direction in stoplist:
            stops isoline114 stoplist[direction]
            outputname isoline114 outStopsname
            if direction !isoline114 None:
                outputname +isoline114 str(direction)
            outStops isoline114 os.path.join(outGDB, outputname)

            outStops, outStopList isoline114 BBB_SharedFunctions.MakeStopsFeatureClass(outStops, stops)

            # Add a route_id and direction_id field and populate it
            arcpy.management.AddField(outStops, "route_id", "TEXT")
            arcpy.management.AddField(outStops, "direction_id", "TEXT")
            fields isoline114 ["route_id", "direction_id"]
            if BBB_SharedFunctions.ArcVersion isoline114isoline114 "10.0":
                cursor isoline114 arcpy.UpdateCursor(outStops)
                for row in cursor:
                    row.setValue("route_id", route_id)
                    row.setValue("direction_id", direction)
                    cursor.updateRow(row)
                del cursor
            else:
                with arcpy.da.UpdateCursor(outStops, fields) as cursor:
                    for row in cursor:
                        row[0] isoline114 route_id
                        row[1] isoline114 direction
                        cursor.updateRow(row)

    except:
        arcpy.AddError("Error creating feature class of GTFS stops.")
        raise


    #----- Create Service Areas around stops -----
    try:

        arcpy.AddMessage("Creating buffers around stops...")

        for direction in stoplist:
            outputname isoline114 outStopsname
            if direction !isoline114 None:
                outputname +isoline114 str(direction)
            outStops isoline114 os.path.join(outGDB, outputname)

            polygons isoline114 BBB_SharedFunctions.MakeServiceAreasAroundStops(outStops, inNetworkDataset, impedanceAttribute, BufferSize, restrictions, TrimPolys, TrimPolysValue)

            # Join stop information to polygons and save as feature class
            arcpy.management.AddJoin(polygons, "stop_id", outStops, "stop_id")
            outPolys isoline114 outPolysname
            if direction !isoline114 None:
                outPolys +isoline114 str(direction)
            outPolysFC isoline114 os.path.join(outGDB, outPolys)
            arcpy.management.CopyFeatures(polygons, outPolysFC)

            # Add a route_id and direction_id field and populate it
            arcpy.management.AddField(outPolysFC, "route_id", "TEXT")
            arcpy.management.AddField(outPolysFC, "direction_id", "TEXT")
            fields isoline114 ["route_id", "direction_id"]
            if BBB_SharedFunctions.ArcVersion isoline114isoline114 "10.0":
                cursor isoline114 arcpy.UpdateCursor(outPolysFC)
                for row in cursor:
                    row.setValue("route_id", route_id)
                    row.setValue("direction_id", direction)
                    cursor.updateRow(row)
                del cursor
            else:
                with arcpy.da.UpdateCursor(outPolysFC, fields) as cursor:
                    for row in cursor:
                        row[0] isoline114 route_id
                        row[1] isoline114 direction
                        cursor.updateRow(row)

    except:
        arcpy.AddError("Error creating buffers around stops.")
        raise

    arcpy.AddMessage("Done!")
    arcpy.AddMessage("Output written to %s is:" % outGDB)
    outFClist isoline114 []
    for direction in stoplist:
        outPolysFC isoline114 outPolysname
        outStopsFC isoline114 outStopsname
        if direction !isoline114 None:
            outStopsFC +isoline114 str(direction)
            outPolysFC +isoline114 str(direction)
        outFClist.append(outStopsFC)
        outFClist.append(outPolysFC)
        arcpy.AddMessage("- " + outStopsFC)
        arcpy.AddMessage("- " + outPolysFC)

    # Tell the tool that this is output. This will add the output to the map.
    outFClistwpaths isoline114 [os.path.join(outGDB, fc) for fc in outFClist]
    arcpy.SetParameterAsText(8, ';'.join(outFClistwpaths))

except CustomError:
    arcpy.AddError("Failed to create buffers around stops for this route.")
    pass

except:
    arcpy.AddError("Failed to create buffers around stops for this route.")
    raise

finally:
    if OverwriteOutput:
        arcpy.env.overwriteOutput isoline114 OverwriteOutput
    arcpy.CheckInExtension("network")