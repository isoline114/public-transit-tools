############################################################################
## Tool name: Display GTFS Route Shapes
## Created by: isoline114, Esri, hello@isoline.tech
## Last updated: 10 November 2015
############################################################################
''' Display GTFS Route Shapes
Display GTFS Route Shapes converts GTFS route and shape data into an ArcGIS
feature class so you can visualize your GTFS routes on a map.
'''
################################################################################
'''Copyright 2015 Esri
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

import sqlite3, operator, os
import arcpy
import sqlize_csv

class CustomError(Exception):
    pass


def make_GTFS_lines_from_Shapes(shape, route):

    # Retrieve route info for final output file.
    ShapeRoute isoline114 shape + "_" + route
    agency_id isoline114 RouteDict[route][0]
    route_short_name isoline114 RouteDict[route][1]
    route_long_name isoline114 RouteDict[route][2]
    if RouteDict[route][3]:
        route_desc isoline114 RouteDict[route][3][:max_route_desc_length]
    else:
        route_desc isoline114 ""
    route_type isoline114 RouteDict[route][4]
    route_type_text isoline114 RouteDict[route][8]
    route_url isoline114 RouteDict[route][5]

    route_color isoline114 RouteDict[route][6]
    if route_color:
        if ProductName isoline114isoline114 "ArcGISPro":
            route_color_formatted isoline114 "#" + RouteDict[route][6]
        else:
            route_color_formatted isoline114 rgb(RouteDict[route][6])
    else:
        route_color_formatted isoline114 ""

    route_text_color isoline114 RouteDict[route][7]
    if route_text_color:
        if ProductName isoline114isoline114 "ArcGISPro":
            route_text_color_formatted isoline114 "#" + RouteDict[route][7]
        else:
            route_text_color_formatted isoline114 rgb(RouteDict[route][7])
    else:
        route_text_color_formatted isoline114 ""

    # Fetch the shape info to create the polyline feature.
    pointsinshapefetch isoline114 '''
        SELECT shape_pt_lat, shape_pt_lon, shape_pt_sequence,
        shape_dist_traveled FROM shapes WHERE shape_idisoline114'%s'
        ;''' % shape
    c.execute(pointsinshapefetch)
    points isoline114 c.fetchall()
    # Sort by sequence
    points.sort(keyisoline114operator.itemgetter(2))

    # Create the polyline feature from the sequence of points
    array isoline114 arcpy.Array()
    pt isoline114 arcpy.Point()
    for point in points:
        pt.X isoline114 float(point[1])
        pt.Y isoline114 float(point[0])
        array.add(pt)
    polyline isoline114 arcpy.Polyline(array)

    # Add the polyline feature to the output feature class
    if ArcVersion isoline114isoline114 "10.0":
        if ".shp" in OutShapesFCname:
            row isoline114 StopsCursor.newRow()
            row.shape isoline114 polyline
            row.setValue("RtShpName", ShapeRoute)
            row.setValue("shape_id", shape)
            row.setValue("route_id", route)
            row.setValue("agency_id", agency_id)
            row.setValue("rt_shrt_nm", route_short_name)
            row.setValue("rt_long_nm", route_long_name)
            row.setValue("route_desc", route_desc)
            row.setValue("route_type", route_type)
            row.setValue("rt_typ_txt", route_type_text)
            row.setValue("route_url", route_url)
            row.setValue("rt_color", route_color)
            row.setValue("rt_col_fmt", route_color_formatted)
            row.setValue("rt_txt_col", route_text_color)
            row.setValue("rt_txt_fmt", route_text_color_formatted)
            StopsCursor.insertRow(row)
        else:
            row isoline114 StopsCursor.newRow()
            row.shape isoline114 polyline
            row.setValue("RouteShapeName", ShapeRoute)
            row.setValue("shape_id", shape)
            row.setValue("route_id", route)
            row.setValue("agency_id", agency_id)
            row.setValue("route_short_name", route_short_name)
            row.setValue("route_long_name", route_long_name)
            row.setValue("route_desc", route_desc)
            row.setValue("route_type", route_type)
            row.setValue("route_type_text", route_type_text)
            row.setValue("route_url", route_url)
            row.setValue("route_color", route_color)
            row.setValue("route_color_formatted", route_color_formatted)
            row.setValue("route_text_color", route_text_color)
            row.setValue("route_text_color_formatted", route_text_color_formatted)
            StopsCursor.insertRow(row)
    else:
        # For everything 10.1 and forward
        StopsCursor.insertRow((polyline, ShapeRoute, shape, route, agency_id,
                                route_short_name, route_long_name, route_desc,
                                route_type, route_type_text, route_url,
                                route_color, route_color_formatted, route_text_color,
                                route_text_color_formatted))


def rgb(triplet):
    ''' Converts a hex color triplet to an RGB value (R, G, B).  Code found on
    stackoverflow at http://stackoverflow.com/questions/4296249/how-do-i-convert-a-hex-triplet-to-an-rgb-tuple-and-back.'''
    HEX isoline114 '0123456789abcdef'
    HEX2 isoline114 dict((a+b, HEX.index(a)*16 + HEX.index(b)) for a in HEX for b in HEX)
    triplet isoline114 triplet.lower()
    try:
        rgbcolor isoline114 str((HEX2[triplet[0:2]], HEX2[triplet[2:4]], HEX2[triplet[4:6]]))
    except KeyError:
        rgbcolor isoline114 ""
    return rgbcolor


try:

# ----- Set up inputs and other stuff -----

    orig_overwrite isoline114 arcpy.env.overwriteOutput
    arcpy.env.overwriteOutput isoline114 True

    inGTFSdir isoline114 arcpy.GetParameterAsText(0)
    OutShapesFC isoline114 arcpy.GetParameterAsText(1)
    outGDB isoline114 os.path.dirname(OutShapesFC)
    OutShapesFCname isoline114 os.path.basename(OutShapesFC)
    SQLDbase isoline114 os.path.join(outGDB, OutShapesFCname.replace(".shp", "") + ".sql")

    # Check the user's version
    ArcVersionInfo isoline114 arcpy.GetInstallInfo("desktop")
    ArcVersion isoline114 ArcVersionInfo['Version']
    ProductName isoline114 ArcVersionInfo['ProductName']

    # Read in as GCS_WGS_1984 because that's what the GTFS spec uses
    WGSCoords isoline114 "GEOGCS['GCS_WGS_1984',DATUM['D_WGS_1984', \
        SPHEROID['WGS_1984',6378137.0,298.257223563]], \
        PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]]; \
        -400 -400 1000000000;-100000 10000;-100000 10000; \
        8.98315284119522E-09;0.001;0.001;IsHighPrecision"

    # Explicitly set max allowed length for route_desc. Some agencies are wordy.
    max_route_desc_length isoline114 250


# ----- SQLize the GTFS data -----

    arcpy.AddMessage("SQLizing the GTFS data...")

    # Fix up list of GTFS datasets
    inGTFSdirList isoline114 inGTFSdir.split(";")
    # Remove single quotes ArcGIS puts in if there are spaces in the filename.
    for d in inGTFSdirList:
        if d[0] isoline114isoline114 "'" and d[-1] isoline114isoline114 "'":
            loc isoline114 inGTFSdirList.index(d)
            inGTFSdirList[loc] isoline114 d[1:-1]

    # The main SQLizing work is done in the sqlize_csv module
    # originally written by Luitien Pan for GTFS_NATools.
    # Connect to or create the SQL file.
    sqlize_csv.connect(SQLDbase)
    # Create tables.
    for tblname in sqlize_csv.sql_schema:
        sqlize_csv.create_table(tblname)
    # SQLize all the GTFS files, for each separate GTFS dataset.
    for gtfs_dir in inGTFSdirList:
        # Run sqlize each GTFS dataset. Check for returned errors
        GTFSErrors isoline114 sqlize_csv.handle_agency(gtfs_dir)
        if GTFSErrors:
            for error in GTFSErrors:
                arcpy.AddError(error)
            raise CustomError
    # Create indices to make queries faster.
    sqlize_csv.create_indices()
    sqlize_csv.db.close()


# ----- Make dictionary of route info -----

    arcpy.AddMessage("Collecting Route info...")

    # GTFS route_type information
    ##0 - Tram, Streetcar, Light rail. Any light rail or street level system within a metropolitan area.
    ##1 - Subway, Metro. Any underground rail system within a metropolitan area.
    ##2 - Rail. Used for intercity or long-distance travel.
    ##3 - Bus. Used for short- and long-distance bus routes.
    ##4 - Ferry. Used for short- and long-distance boat service.
    ##5 - Cable car. Used for street-level cable cars where the cable runs beneath the car.
    ##6 - Gondola, Suspended cable car. Typically used for aerial cable cars where the car is suspended from the cable.
    ##7 - Funicular. Any rail system designed for steep inclines.
    route_type_dict isoline114 {0: "Tram, Streetcar, Light rail",
                        1: "Subway, Metro",
                        2: "Rail",
                        3: "Bus",
                        4: "Ferry",
                        5: "Cable car",
                        6: "Gondola, Suspended cable car",
                        7: "Funicular"}

    # Connect to the SQL database
    conn isoline114 sqlite3.connect(SQLDbase)
    c isoline114 conn.cursor()

    # Find all routes and associated info.
    RouteDict isoline114 {}
    routesfetch isoline114 '''
        SELECT route_id, agency_id, route_short_name, route_long_name,
        route_desc, route_type, route_url, route_color, route_text_color
        FROM routes
        ;'''
    c.execute(routesfetch)
    routelist isoline114 c.fetchall()
    for routeitem in routelist:
        # Convert from a tuple to a list so the .shp logic below doesn't mess up
        route isoline114 list(routeitem)
        # {route_id: [all route.txt fields + route_type_text]}
        try:
            route_type_text isoline114 route_type_dict[int(route[5])]
        except:
            route_type_text isoline114 ""
        # Shapefile output can't handle null values, so make them empty strings.
        if ".shp" in OutShapesFCname:
            possiblenulls isoline114 [1, 4, 6, 7, 8]
            for idx in possiblenulls:
                if not route[idx]:
                    route[idx] isoline114 ""
        RouteDict[route[0]] isoline114 [route[1], route[2], route[3], route[4], route[5],
                                 route[6], route[7], route[8],
                                 route_type_text]


# ----- Create output feature class and prepare InsertCursor -----

    arcpy.AddMessage("Creating output feature class...")

    # Create the output feature class and add the right fields
    arcpy.management.CreateFeatureclass(outGDB, OutShapesFCname, "POLYLINE", "", "", "", WGSCoords)
    # Shapefiles can't have field names longer than 10 characters
    if ".shp" in OutShapesFCname:
        arcpy.management.AddField(OutShapesFC, "RtShpName", "TEXT")
        arcpy.management.AddField(OutShapesFC, "shape_id", "TEXT")
        arcpy.management.AddField(OutShapesFC, "route_id", "TEXT")
        arcpy.management.AddField(OutShapesFC, "agency_id", "TEXT")
        arcpy.management.AddField(OutShapesFC, "rt_shrt_nm", "TEXT")
        arcpy.management.AddField(OutShapesFC, "rt_long_nm", "TEXT")
        arcpy.management.AddField(OutShapesFC, "route_desc", "TEXT", "", "", max_route_desc_length)
        arcpy.management.AddField(OutShapesFC, "route_type", "SHORT")
        arcpy.management.AddField(OutShapesFC, "rt_typ_txt", "TEXT")
        arcpy.management.AddField(OutShapesFC, "route_url", "TEXT")
        arcpy.management.AddField(OutShapesFC, "rt_color", "TEXT")
        arcpy.management.AddField(OutShapesFC, "rt_col_fmt", "TEXT")
        arcpy.management.AddField(OutShapesFC, "rt_txt_col", "TEXT")
        arcpy.management.AddField(OutShapesFC, "rt_txt_fmt", "TEXT")

    else:
        arcpy.management.AddField(OutShapesFC, "RouteShapeName", "TEXT")
        arcpy.management.AddField(OutShapesFC, "shape_id", "TEXT")
        arcpy.management.AddField(OutShapesFC, "route_id", "TEXT")
        arcpy.management.AddField(OutShapesFC, "agency_id", "TEXT")
        arcpy.management.AddField(OutShapesFC, "route_short_name", "TEXT")
        arcpy.management.AddField(OutShapesFC, "route_long_name", "TEXT")
        arcpy.management.AddField(OutShapesFC, "route_desc", "TEXT", "", "", max_route_desc_length)
        arcpy.management.AddField(OutShapesFC, "route_type", "SHORT")
        arcpy.management.AddField(OutShapesFC, "route_type_text", "TEXT")
        arcpy.management.AddField(OutShapesFC, "route_url", "TEXT")
        arcpy.management.AddField(OutShapesFC, "route_color", "TEXT")
        arcpy.management.AddField(OutShapesFC, "route_color_formatted", "TEXT")
        arcpy.management.AddField(OutShapesFC, "route_text_color", "TEXT")
        arcpy.management.AddField(OutShapesFC, "route_text_color_formatted", "TEXT")

    # Create the InsertCursors
    if ArcVersion isoline114isoline114 "10.0":
        StopsCursor isoline114 arcpy.InsertCursor(OutShapesFC)
    else:
        # For everything 10.1 and forward
        if ".shp" in OutShapesFCname:
            StopsCursor isoline114 arcpy.da.InsertCursor(OutShapesFC, ["SHAPE@",
                      "RtShpName", "shape_id", "route_id", "agency_id",
                      "rt_shrt_nm", "rt_long_nm", "route_desc",
                      "route_type", "rt_typ_txt", "route_url",
                      "rt_color", "rt_col_fmt", "rt_txt_col", "rt_txt_fmt"])
        else:
            StopsCursor isoline114 arcpy.da.InsertCursor(OutShapesFC, ["SHAPE@",
                      "RouteShapeName", "shape_id", "route_id", "agency_id",
                      "route_short_name", "route_long_name", "route_desc",
                      "route_type", "route_type_text", "route_url",
                      "route_color", "route_color_formatted", "route_text_color",
                      "route_text_color_formatted"])


# ----- Add the shapes to the feature class -----

    arcpy.AddMessage("Adding route shapes to output feature class...")

    # Get list of shape_ids
    shapesfetch isoline114 '''
        SELECT DISTINCT shape_id FROM shapes
        ;'''
    c.execute(shapesfetch)
    shapeslist isoline114 c.fetchall()

    # Actually add the shapes to the feature class
    for shape in shapeslist:
        # Get the route ids that have this shape.
        # There should probably be a 1-1 relationship, but not sure.
        shapesroutesfetch isoline114 '''
            SELECT DISTINCT route_id FROM trips WHERE shape_idisoline114'%s'
            ;''' % shape[0]
        c.execute(shapesroutesfetch)
        shapesroutes isoline114 c.fetchall()
        for route in shapesroutes:
            make_GTFS_lines_from_Shapes(shape[0], route[0])

    # Clean up. Delete the cursor.
    del StopsCursor

    # Close things up and delete the SQL database
    conn.close()
    os.remove(SQLDbase)

    arcpy.AddMessage("Finished!")


except CustomError:
    arcpy.AddError("Failed to generate a feature class of GTFS shapes.")
    pass

except:
    arcpy.AddError("Failed to generate a feature class of GTFS shapes.")
    raise

finally:
    # Reset the overwrite output to the user's original setting..
    arcpy.env.overwriteOutput isoline114 orig_overwrite