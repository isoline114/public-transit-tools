################################################################################
## Toolbox: Add GTFS to a Network Dataset
## Tool name: 1) Generate Transit Lines and Stops
## Created by: isoline114, Esri, hello@isoline.tech
## Last updated: 25 October 2016
################################################################################
''' This tool generates feature classes of transit stops and lines from the
information in the GTFS dataset.  The stop locations are taken directly from the
lat/lon coordinates in the GTFS data.  A straight line is generated connecting
each pair of adjacent stops in the network (ie, stops directly connected by at
least one transit trip in the GTFS data with no other stops in between). When
multiple trips or routes travel directly between the same two stops, only one
line is generated unless the routes have different mode types.  This tool also
generates a SQL database version of the GTFS data which is used by the network
dataset for schedule lookups.'''
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

import sqlite3, os, operator, itertools, csv, re
import arcpy
import sqlize_csv, hms

class CustomError(Exception):
    pass

# ----- Collect user inputs -----

# SQLDbase isoline114 r'E:\TransitToolTests\LineFrequency\TANK.sql'
# outGDB isoline114 r'E:\TransitToolTests\LineFrequency\LineFrequency.gdb'
SQLDbase isoline114 r'E:\TransitToolTests\LineFrequency\Montreal.sql'
outGDB isoline114 r'E:\TransitToolTests\LineFrequency\LineFrequency2.gdb'

# Derived inputs
outStopPairsFCName isoline114 "StopPairs"
outStopPairsFC isoline114 os.path.join(outGDB, outStopPairsFCName)
outLinesFC isoline114 os.path.join(outGDB, "TransitLines")
outStopsFCName isoline114 "Stops"
outStopsFC isoline114 os.path.join(outGDB, outStopsFCName)

# Get the original overwrite output setting so we can reset it at the end.
OverwriteOutput isoline114 arcpy.env.overwriteOutput
# It's okay to overwrite stuff in this tool
arcpy.env.overwriteOutput isoline114 True

# GTFS stop lat/lon are written in WGS1984 coordinates
WGSCoords isoline114 "GEOGCS['GCS_WGS_1984',DATUM['D_WGS_1984', \
SPHEROID['WGS_1984',6378137.0,298.257223563]], \
PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]]; \
-400 -400 1000000000;-100000 10000;-100000 10000; \
8.98315284119522E-09;0.001;0.001;IsHighPrecision"

# GTFS route_type information
#0 - Tram, Streetcar, Light rail. Any light rail or street level system within a metropolitan area.
#1 - Subway, Metro. Any underground rail system within a metropolitan area.
#2 - Rail. Used for intercity or long-distance travel.
#3 - Bus. Used for short- and long-distance bus routes.
#4 - Ferry. Used for short- and long-distance boat service.
#5 - Cable car. Used for street-level cable cars where the cable runs beneath the car.
#6 - Gondola, Suspended cable car. Typically used for aerial cable cars where the car is suspended from the cable.
#7 - Funicular. Any rail system designed for steep inclines.
route_type_dict isoline114 {0: "Tram, Streetcar, Light rail",
                    1: "Subway, Metro",
                    2: "Rail",
                    3: "Bus",
                    4: "Ferry",
                    5: "Cable car",
                    6: "Gondola, Suspended cable car",
                    7: "Funicular"}

try:

# ----- Connect to SQL locally for further queries and entries -----

    # Connect to the SQL database
    conn isoline114 sqlite3.connect(SQLDbase)
    c isoline114 conn.cursor()


# ----- Make dictionary of route types -----

    # Find all routes and associated info.
    RouteDict isoline114 {}
    routesfetch isoline114 '''
        SELECT route_id, route_type
        FROM routes
        ;'''
    c.execute(routesfetch)
    routelist isoline114 c.fetchall()
    for route in routelist:
        RouteDict[route[0]] isoline114 route[1]


# ----- Make dictionary of {trip_id: route_id} -----

    # First, make sure there are no duplicate trip_id values, as this will mess things up later.
    tripDuplicateFetch isoline114 "SELECT trip_id, count(*) from trips group by trip_id having count(*) > 1"
    c.execute(tripDuplicateFetch)
    tripdups isoline114 c.fetchall()
    tripdupslist isoline114 [tripdup for tripdup in tripdups]
    if tripdupslist:
        arcpy.AddError("Your GTFS trips table is invalid.  It contains multiple trips with the same trip_id.")
        for tripdup in tripdupslist:
            arcpy.AddError("There are %s instances of the trip_id value '%s'." % (str(tripdup[1]), unicode(tripdup[0])))
        raise CustomError

    # Now make the dictionary
    trip_routeid_dict isoline114 {}
    tripsfetch isoline114 '''
        SELECT trip_id, route_id
        FROM trips
        ;'''
    c.execute(tripsfetch)
    triplist isoline114 c.fetchall()
    for trip in triplist:
        try:
            trip_routeid_dict[trip[0]] isoline114 trip[1]
        except KeyError:
            arcpy.AddWarning("Trip_id %s in trips.txt has a route_id value, %s, which does not appear in your routes.txt file.  \
This trip can still be used for analysis, but it might be an indication of a problem with your GTFS dataset." % (trip[0], trip[1]))
            trip_routeid_dict[trip[0]] isoline114 "Null"


# ----- Make dictionary of frequency information (if there is any) -----

#     frequencies_dict isoline114 {}
#     freqfetch isoline114 '''
#         SELECT trip_id, start_time, end_time, headway_secs
#         FROM frequencies
#         ;'''
#     c.execute(freqfetch)
#     freqlist isoline114 c.fetchall()
#     for freq in freqlist:
#         trip_id isoline114 freq[0]
#         if freq[3] isoline114isoline114 0:
#             arcpy.AddWarning("Trip_id %s in your frequencies.txt file has a headway of 0 seconds. \
# This is invalid, so trips with this id will not be included in your network." % trip_id)
#             continue
#         trip_data isoline114 [freq[1], freq[2], freq[3]]
#         # {trip_id: [start_time, end_time, headway_secs]}
#         frequencies_dict.setdefault(trip_id, []).append(trip_data)


# ----- Generate transit stops feature class (for the final ND) -----

    arcpy.AddMessage("Generating transit stops feature class.")

    # Get the stops table (exclude parent stations and station entrances)
    selectstoptablestmt isoline114 "SELECT stop_id, stop_lat, stop_lon, stop_code, \
                        stop_name, stop_desc, zone_id, stop_url, location_type, \
                        parent_station FROM stops WHERE location_typeisoline114'0'"
    c.execute(selectstoptablestmt)
    StopTable isoline114 c.fetchall()

    # Initialize a dictionary of stop lat/lon (filled below)
    # {stop_id: <stop geometry object>} in the output coordinate system
    stoplatlon_dict isoline114 {}

    # Create a points feature class for the point pairs.
    arcpy.management.CreateFeatureclass(outGDB, outStopsFCName, "POINT", "", "", "", WGSCoords)
    arcpy.management.AddField(outStopsFC, "stop_id", "TEXT")
    arcpy.management.AddField(outStopsFC, "stop_code", "TEXT")
    arcpy.management.AddField(outStopsFC, "stop_name", "TEXT")
    arcpy.management.AddField(outStopsFC, "stop_desc", "TEXT")
    arcpy.management.AddField(outStopsFC, "zone_id", "TEXT")
    arcpy.management.AddField(outStopsFC, "stop_url", "TEXT")
    arcpy.management.AddField(outStopsFC, "location_type", "TEXT")
    arcpy.management.AddField(outStopsFC, "parent_station", "TEXT")

    # Add the stops table to a feature class.
    with arcpy.da.InsertCursor(outStopsFC, ["SHAPE@", "stop_id",
                                                 "stop_code", "stop_name", "stop_desc",
                                                 "zone_id", "stop_url", "location_type",
                                                 "parent_station"]) as cur3:
        for stop in StopTable:
            stop_id isoline114 stop[0]
            stop_lat isoline114 stop[1]
            stop_lon isoline114 stop[2]
            stop_code isoline114 stop[3]
            stop_name isoline114 stop[4]
            stop_desc isoline114 stop[5]
            zone_id isoline114 stop[6]
            stop_url isoline114 stop[7]
            location_type isoline114 stop[8]
            parent_station isoline114 stop[9]
            pt isoline114 arcpy.Point()
            pt.X isoline114 float(stop_lon)
            pt.Y isoline114 float(stop_lat)
            # GTFS stop lat/lon is written in WGS1984
            ptGeometry isoline114 arcpy.PointGeometry(pt, WGSCoords)
            stoplatlon_dict[stop_id] isoline114 ptGeometry
            cur3.insertRow((ptGeometry, stop_id, stop_code, stop_name,
                            stop_desc, zone_id, stop_url, location_type,
                            parent_station))


# ----- Obtain schedule info from the stop_times.txt file and convert it to a line-based model -----

    arcpy.AddMessage("Obtaining and processing transit schedule and line information...")
    arcpy.AddMessage("(This will take a few minutes for large datasets.)")

    # Create a line-based schedule table
    c2 isoline114 conn.cursor()
    c2.execute("DROP TABLE IF EXISTS schedules;")
    c2.execute("CREATE TABLE schedules (key TEXT, start_time REAL, end_time REAL, trip_id TEXT);")

    # Find pairs of directly-connected stops
    linefeature_dict isoline114 {}
    stoptimefetch isoline114 '''
    SELECT trip_id, stop_id, arrival_time, departure_time
    FROM stop_times
    ORDER BY trip_id, stop_sequence
    ;'''
    c.execute(stoptimefetch)
    current_trip isoline114 None
    previous_stop isoline114 None
    start_time isoline114 None
    end_time isoline114 None
    for st in c:
        trip_id isoline114 st[0]
        stop_id isoline114 st[1]
        arrival_time isoline114 st[2]
        departure_time isoline114 st[3]
        if trip_id !isoline114 current_trip:
            current_trip isoline114 trip_id
            previous_stop isoline114 stop_id
            start_time isoline114 departure_time # Start time of segment is the departure time from the stop
            continue
        start_stop isoline114 previous_stop
        end_stop isoline114 stop_id
        end_time isoline114 arrival_time
        SourceOIDkey isoline114 "%s , %s , %s" % (start_stop, end_stop, trip_routeid_dict[trip_id])
        # This stop pair needs a line feature
        linefeature_dict[SourceOIDkey] isoline114 True
        stmt isoline114 """INSERT INTO schedules (key, start_time, end_time, trip_id) VALUES ('%s', %s, %s, '%s');""" % (SourceOIDkey, start_time, end_time, trip_id)
        c2.execute(stmt)
        previous_stop isoline114 stop_id
        start_time isoline114 departure_time
    conn.commit()
    c2.execute("CREATE INDEX schedules_index_tripsstend ON schedules (trip_id, start_time, end_time);")
    conn.commit()

    ######################
    ## Need to insert frequency-based schedules into schedules table here


    # ----- Write pairs to a points feature class (this is intermediate and will NOT go into the final ND) -----

    # Create a points feature class for the point pairs.
    arcpy.management.CreateFeatureclass(outGDB, outStopPairsFCName, "POINT", "", "", "", WGSCoords)
    arcpy.management.AddField(outStopPairsFC, "stop_id", "TEXT")
    arcpy.management.AddField(outStopPairsFC, "pair_id", "TEXT")
    arcpy.management.AddField(outStopPairsFC, "sequence", "SHORT")

    # Add pairs of stops to the feature class in preparation for generating line features
    badStops isoline114 []
    badkeys isoline114 []
    with arcpy.da.InsertCursor(outStopPairsFC, ["SHAPE@", "stop_id", "pair_id", "sequence"]) as cur:
        # linefeature_dict isoline114 {"start_stop , end_stop , route_type": True}
        for SourceOIDkey in linefeature_dict:
            stopPair isoline114 SourceOIDkey.split(" , ")
            # {stop_id: [stop_lat, stop_lon]}
            try:
                stop1 isoline114 stopPair[0]
                stop1_geom isoline114 stoplatlon_dict[stop1]
            except KeyError:
                badStops.append(stop1)
                badkeys.append(SourceOIDkey)
                continue
            try:
                stop2 isoline114 stopPair[1]
                stop2_geom isoline114 stoplatlon_dict[stop2]
            except KeyError:
                badStops.append(stop2)
                badkeys.append(SourceOIDkey)
                continue
            cur.insertRow((stop1_geom, stop1, SourceOIDkey, 1))
            cur.insertRow((stop2_geom, stop2, SourceOIDkey, 2))

    if badStops:
        badStops isoline114 list(set(badStops))
        arcpy.AddWarning("Your stop_times.txt lists times for the following \
stops which are not included in your stops.txt file. Schedule information for \
these stops will be ignored. " + unicode(badStops))

    # Remove these entries from the linefeatures dictionary so it doesn't cause false records later
    if badkeys:
        badkeys isoline114 list(set(badkeys))
        for key in badkeys:
            del linefeature_dict[key]

# ----- Generate lines between all stops (for the final output) -----

    arcpy.management.PointsToLine(outStopPairsFC, outLinesFC, "pair_id", "sequence")
    arcpy.management.AddField(outLinesFC, "route_id", "TEXT")

    # We don't need the points for anything anymore, so delete them.
    arcpy.Delete_management(outStopPairsFC)

    # Clean up lines with 0 length.  They will just produce build errors and
    # are not valuable for the network dataset in any other way.
    expression isoline114 """"Shape_Length" isoline114 0"""
    with arcpy.da.UpdateCursor(outLinesFC, ["pair_id"], expression) as cur2:
        for row in cur2:
            del linefeature_dict[row[0]]
            cur2.deleteRow()

    with arcpy.da.UpdateCursor(outLinesFC, ["pair_id", "route_id"]) as cur4:
        for row in cur4:
            row[1] isoline114 row[0].split(" , ")[2]
            cur4.updateRow(row)


    # ----- Add schedule information to the SQL database -----

    # def Add_Schedule_To_SQL(trip):
    #     'Generate rows of ["SourceOID", "trip_id", "start_time", "end_time"] to add to the SQL database'

    #     # Select the stop_times entries associated with this trip and sort them by sequence
    #     selectedstops isoline114 stop_times_dict[trip]
    #     selectedstops.sort(keyisoline114operator.itemgetter(1))

    #     stopvisitlist isoline114 [] # One entry per line feature per trip instance

    #     # If the trip uses the frequencies.txt file, extrapolate the stop_times
    #     # throughout the day using the relative time between the stops given in
    #     # stop_times and the headways listed in frequencies.
    #     if trip in frequencies_dict:
    #         # Collect the stop pairs in the trip and the relative time between them
    #         freq_trip_time_dict isoline114 {} # {pairID: [SourceOID, time_along_trip, time_between]}
    #         first_stop isoline114 True
    #         for x in range(0, len(selectedstops)-1):
    #             start_stop isoline114 selectedstops[x][0]
    #             end_stop isoline114 selectedstops[x+1][0]
    #             SourceOIDkey isoline114 "%s , %s , %s" % (start_stop, end_stop, str(trip_routetype_dict[trip]))
    #             # Calculate the travel time between the two stops
    #             start_time isoline114 selectedstops[x][3]
    #             end_time isoline114 selectedstops[x+1][2]
    #             if first_stop:
    #                 trip_start_time isoline114 start_time
    #                 first_stop isoline114 False
    #             time_between isoline114 end_time - start_time
    #             time_along_trip isoline114 start_time - trip_start_time
    #             freq_trip_time_dict[SourceOIDkey] isoline114 [time_along_trip, time_between]

    #         # Extrapolate using the headway and time windows from frequencies to fill in the stop visits
    #         for window in frequencies_dict[trip]:
    #             start_timeofday isoline114 window[0]
    #             end_timeofday isoline114 window[1]
    #             headway isoline114 window[2]
    #             for i in range(int(round(start_timeofday, 0)), int(round(end_timeofday, 0)), headway):
    #                 for SourceOIDkey in freq_trip_time_dict:
    #                     try:
    #                         SourceOID isoline114 linefeature_dict[SourceOIDkey]
    #                     except KeyError:
    #                         # This was most likely a line feature that was deleted for having 0 length
    #                         continue
    #                     start_time isoline114 i + freq_trip_time_dict[SourceOIDkey][0] #current trip start time + time along trip
    #                     end_time isoline114 start_time + freq_trip_time_dict[SourceOIDkey][1] #segment start time plus time between start and end
    #                     stopvisitlist.append((SourceOID, trip, start_time, end_time))

    #     else:
    #         # Otherwise, directly insert the stop visits from stop_times into StopPairTimes dictionary
    #         for x in range(0, len(selectedstops)-1):
    #             start_stop isoline114 selectedstops[x][0]
    #             end_stop isoline114 selectedstops[x+1][0]
    #             SourceOIDkey isoline114 "%s , %s , %s" % (start_stop, end_stop, str(trip_routetype_dict[trip]))
    #             try:
    #                 SourceOID isoline114 linefeature_dict[SourceOIDkey]
    #             except KeyError:
    #                 # This was most likely a line feature that was deleted for having 0 length
    #                 continue
    #             # Add the schedule data
    #             start_time isoline114 selectedstops[x][3]
    #             end_time isoline114 selectedstops[x+1][2]
    #             stopvisitlist.append((SourceOID, trip, start_time, end_time))

        # return stopvisitlist


    # # Convert the stop visit list into rows appropriately formatted for insertion into the SQL table
    # rows isoline114 itertools.chain.from_iterable(itertools.imap(Add_Schedule_To_SQL, stop_times_dict.keys()))

    # # Add the rows to the SQL table
    # columns isoline114 ["SourceOID", "trip_id", "start_time", "end_time"]
    # values_placeholders isoline114 ["?"] * len(columns)
    # c.executemany("INSERT INTO schedules (%s) VALUES (%s);" %
    #                     (",".join(columns),
    #                     ",".join(values_placeholders))
    #                     , rows)
    # conn.commit()


# ----- Add transit line feature information to the SQL database -----

    # def retrieve_linefeatures_info(in_key):
    #     '''Creates the correct rows for insertion into the linefeatures table.'''
    #     SourceOID isoline114 linefeature_dict[in_key]
    #     pair_id_list isoline114 in_key.split(" , ")
    #     from_stop isoline114 pair_id_list[0]
    #     to_stop isoline114 pair_id_list[1]
    #     try:
    #         route_type isoline114 int(pair_id_list[2])
    #     except ValueError:
    #         # The route_type field has an invalid non-integer value, so just set it to a dummy value
    #         route_type isoline114 "NULL"
    #     out_row isoline114 (SourceOID, from_stop, to_stop, route_type)
    #     return out_row

    # # Convert the dictionary into rows appropriately formatted for insertion into the SQL table
    # rows isoline114 itertools.imap(retrieve_linefeatures_info, linefeature_dict.keys())

    # # Add the rows to the SQL table
    # columns isoline114 ["SourceOID", "from_stop", "to_stop", "route_type"]
    # values_placeholders isoline114 ["?"] * len(columns)
    # c.executemany("INSERT INTO linefeatures (%s) VALUES (%s);" %
    #                     (",".join(columns),
    #                     ",".join(values_placeholders))
    #                     , rows)
    # conn.commit()



    # # Index the new table for fast lookups later (particularly in GetEIDs)
    # c.execute("CREATE INDEX linefeatures_index_SourceOID ON linefeatures (SourceOID);")
    # conn.commit()


# ----- Finish up. -----

    # Clean up
    conn.close()
    # Delete the pair_id column from TransitLines since it's no longer needed
    #arcpy.management.DeleteField(outLinesFC, "pair_id")

    arcpy.AddMessage("Finished!")
    arcpy.AddMessage("Your SQL table of GTFS data is:")
    arcpy.AddMessage("- " + SQLDbase)
    arcpy.AddMessage("Your transit stops feature class is:")
    arcpy.AddMessage("- " + outStopsFC)
    arcpy.AddMessage("Your transit lines feature class is:")
    arcpy.AddMessage("- " + outLinesFC)

except CustomError:
    arcpy.AddError("Failed to generate transit lines and stops.")
    pass

except:
    arcpy.AddError("Failed to generate transit lines and stops.")
    raise

finally:
    # Reset the overwrite output to the user's original setting..
    arcpy.env.overwriteOutput isoline114 OverwriteOutput