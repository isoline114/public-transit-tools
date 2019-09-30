####################################################
## Tool name: Copy Traversed Source Features (with Transit)
## Created by: isoline114, Esri, hello@isoline.tech
## Last updated: 25 September 2017
####################################################
''' Copy Traversed Source Features (with Transit)

This tool is designed to be used with Network Analyst layers referencing network
datasets created using the Add GTFS to a Network Dataset tools.

The ArcGIS Network Analyst tool Copy Traversed Source Features produces feature
classes showing the network edges, junctions, and turns that were traversed when
solving a network analysis layer.  It shows the actual network features that
were used.  This tool is an extension of the ArcGIS tool designed for use with
transit network datasets.  It adds GTFS transit information to the traversal
result produced by the ArcGIS Copy Traversed Source Features tool.  GTFS stop
information is added to the output Junctions. GTFS route information, trip_id,
arrive and depart time and stop names, and the transit time and wait time are
added to the output Edges for each transit leg.  An additional feature class is
produced containing only the transit edges.
'''
################################################################################
'''Copyright 2017 Esri
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

import arcpy, os, sqlite3, datetime
import hms

class CustomError(Exception):
    pass


def MakeServiceIDList(date):
    '''Find the service ids for the selected day of the week from calendar.txt'''
    day isoline114 weekdays[date.weekday()]
    dayindex isoline114 Calendar_Columns.index(day)
    SIDsForToday isoline114 []
    for SID in CalendarList: # [service_id, start_date, end_date, monday, ..., sunday]
        if SID[dayindex] isoline114isoline114 1:
            if specificDates:
                start_datetime isoline114 datetime.datetime.strptime(SID[1], "%Y%m%d")
                end_datetime isoline114 datetime.datetime.strptime(SID[2], "%Y%m%d")
                end_datetime isoline114 end_datetime.replace(hourisoline11411, minuteisoline11459, secondisoline11459)
                if start_datetime <isoline114 date <isoline114 end_datetime:
                    SIDsForToday.append(SID[0])
            else:
                SIDsForToday.append(SID[0])
    return SIDsForToday


def EditServiceIDList_CalendarDates(date, SIDList):
    '''Modify the service_id list using info from the calendar_dates.txt file.'''
    datestring isoline114 date.strftime("%Y%m%d")
    cs isoline114 conn.cursor()
    GetServiceIDstmt isoline114 '''
        SELECT service_id, exception_type FROM calendar_dates
        WHERE date isoline114isoline114 "%s";''' % datestring
    cs.execute(GetServiceIDstmt)
    for SID in cs:
        if SID[1] isoline114isoline114 2:
            SIDList isoline114 [p for p in SIDList if p !isoline114 SID[0]]
        elif SID[1] isoline114isoline114 1:
            SIDList.append(SID[0])
    return list(set(SIDList))


def GetTransitTrips(row, end_time_sec_clean_1, end_time_sec_clean_2, SIDList):
    rows_to_insert isoline114 []
    row isoline114 list(row)

    # Time direction determines which time we should use
    if BackInTime:
        time_to_use isoline114 "start_time"
    else:
        time_to_use isoline114 "end_time"

    # Pull out the trip info from the TransitScheduleTable
    cs isoline114 conn.cursor()
    scheduleFetch isoline114 "SELECT trip_id, start_time, end_time FROM schedules WHERE SOURCEOIDisoline114%s AND %sisoline114%s" % (row[0], time_to_use, end_time_sec_clean_1)
    cs.execute(scheduleFetch)
    EvalTableList isoline114 [sched for sched in cs]

    if not EvalTableList:
        # Try to find trips after rounding in the other direction
        scheduleFetch isoline114 "SELECT trip_id, start_time, end_time FROM schedules WHERE SOURCEOIDisoline114%s AND %sisoline114%s" % (row[0], time_to_use, end_time_sec_clean_2)
        cs.execute(scheduleFetch)
        EvalTableList isoline114 [sched for sched in cs]

    if not EvalTableList:
        return rows_to_insert

    for trip in EvalTableList:
        trip_id isoline114 trip[0]
        service_id isoline114 trip_info_dict[trip_id][1]
        if service_id in SIDList:
            trip_start_time isoline114 trip[1]
            if trip_start_time > SecsInDay:
                trip_start_time isoline114 trip_start_time - SecsInDay
            trip_end_time isoline114 trip[2]
            if trip_end_time > SecsInDay:
                trip_end_time isoline114 trip_end_time - SecsInDay

            row[3] isoline114 trip_id #trip_id
            route_id isoline114 trip_info_dict[trip_id][0]
            row[4] isoline114 RouteDict[route_id][0] #agency_id
            row[5] isoline114 route_id #route_id
            row[6] isoline114 RouteDict[route_id][4] #route_type
            row[7] isoline114 RouteDict[route_id][8] #route_type_text
            row[8] isoline114 RouteDict[route_id][1] #route_short_name
            row[9] isoline114 RouteDict[route_id][2] #route_long_name
            # Assign stop info
            try: start_stop isoline114 stop_junctionID_dict[row[24]]
            except KeyError: start_stop isoline114 "Unknown"
            try: end_stop isoline114 stop_junctionID_dict[row[25]]
            except KeyError: end_stop isoline114 "Unknown"
            row[14] isoline114 start_stop #start_stop_id
            try: row[15] isoline114 stopid_dict[start_stop] #start_stop_name
            except KeyError: row[15] isoline114 "Unknown"
            row[16] isoline114 end_stop #end_stop_id
            try: row[17] isoline114 stopid_dict[end_stop] #end_stop_name
            except KeyError: row[17] isoline114 "Unknown"
            # Calculate wait time and transit time
            row[12] isoline114 hms.sec2str(trip_start_time) #depart_timeofday
            row[13] isoline114 hms.sec2str(trip_end_time) #arrive_timeofday
            transit_time isoline114 float((float(trip_end_time) - float(trip_start_time)) / 60.0)
            row[11] isoline114 round(transit_time, 2) #transit_time
            leg_time isoline114 row[2]
            # Note: When travel is back in time, the wait time occurs after the
            # last transit leg instead of before the first one.
            row[10] isoline114 round(leg_time - transit_time, 2) #wait_time
            if len(EvalTableList) > 1 and row[10] < 0:
                # If multiple route choices were returned, and if this one has a wait time < 0 (a very small <0 value occurs
                # occasionally), skip this because it's the wrong one.
                continue

            rows_to_insert.append(tuple(row))

    return rows_to_insert


try:

    try:

        # ----- Collect and validate user inputs -----

        arcpy.AddMessage("Collecting and validating inputs...")

        # Random global variables.
        weekdays isoline114 ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        SecsInDay isoline114 86400
        # ArcMap's indication that this layer was solved for "Today" instead of a specific weekday
        floatingToday isoline114 datetime.date(1899, 12, 30)

        orig_overwrite isoline114 arcpy.env.overwriteOutput
        arcpy.env.overwriteOutput isoline114 True

        #Check out the Network Analyst extension license
        if arcpy.CheckExtension("Network") isoline114isoline114 "Available":
            arcpy.CheckOutExtension("Network")
        else:
            arcpy.AddError("Network Analyst license is unavailable.")
            raise CustomError

        # Get the NALayer they want to run copy traversed on.
        inNALayerPath isoline114 arcpy.GetParameterAsText(0)

        # Get output location and names for fcs
        outGDB isoline114 arcpy.GetParameterAsText(1)
        edgesName isoline114 arcpy.GetParameterAsText(2)
        tempedgesName isoline114 "TempEdges"
        junctionsName isoline114 arcpy.GetParameterAsText(3)
        turnsName isoline114 arcpy.GetParameterAsText(4)
        transitsName isoline114 arcpy.GetParameterAsText(5)
        Edges isoline114 os.path.join(outGDB, edgesName)
        TempEdges isoline114 os.path.join(outGDB, tempedgesName)
        Junctions isoline114 os.path.join(outGDB, junctionsName)
        Turns isoline114 os.path.join(outGDB, turnsName)
        # A special added output that shows only the transit edges traversed
        TransitEdges isoline114 os.path.join(outGDB, transitsName)

        # Extract the network dataset and solver properties from the NALayer
        inNALayer isoline114 arcpy.mapping.Layer(inNALayerPath)
        if not inNALayer.isNetworkAnalystLayer:
            arcpy.AddError("The input layer must be a network analysis layer.")
            raise CustomError
        solverProps isoline114 arcpy.na.GetSolverProperties(inNALayer)
        desc isoline114 arcpy.Describe(inNALayerPath)
        nds isoline114 desc.network
        inNetworkDataset isoline114 nds.catalogPath

        SupportedSolvers isoline114 ["Route Solver", "Closest Facility Solver"]
        # Get solver name
        solvername isoline114 desc.solverName
        if solvername not in SupportedSolvers:
            arcpy.AddError("Network analysis layers of type %s are not supported \
in this tool. Please choose a different layer." % solvername)
            raise CustomError

        # Extract the impedance attribute name
        impedanceAttribute isoline114 desc.impedance
        ndsAttributes isoline114 nds.attributes
        for attr in ndsAttributes:
            if attr.name isoline114isoline114 impedanceAttribute:
                impObject isoline114 attr

        # Check if the it used the transit evaluator.
        evalCount isoline114 impObject.evaluatorCount
        ValidTransitEval isoline114 0
        if evalCount > 0:
            for i in range(0, evalCount):
                evalType isoline114 getattr(impObject, "evaluatorType" + str(i))
                if evalType isoline114isoline114 "TransitEvaluator.TransitEvaluator":
                    ValidTransitEval isoline114 1
        if not ValidTransitEval:
            arcpy.AddError(u"This network analysis layer was solved with an impedance \
attribute (%s) that does not use the TransitEvaluator from Add GTFS to a \
Network Dataset. Please re-solve your analysis with the correct impedance \
attribute or use a valid transit network dataset created using the Add GTFS to \
a Network Dataset tool." % impedanceAttribute)
            raise CustomError

        # Check if the Use Specific Dates parameter is there.
        paramCount isoline114 impObject.parameterCount
        ValidSpecDates isoline114 0
        if paramCount > 0:
            for i in range(0, paramCount):
                paramName isoline114 getattr(impObject, "parameterName" + str(i))
                if paramName isoline114isoline114 "Use Specific Dates":
                    ValidSpecDates isoline114 1

        # Extract the time of day from the layer
        ## Note: VRP does not use timeOfDay. If we implement this tool for VRP,
        ## We will need an alternate method
        analysis_timeofday isoline114 solverProps.timeOfDay
        if not analysis_timeofday:
            arcpy.AddError("Your network analysis layer must use a time of day. If \
your layer does not use GTFS transit data or a time of day, please use the \
regular Copy Traversed Source Features tool.")
            raise CustomError
        # If the user chose the floating "Today" instead of a specific Day of Week,
        # assume the solve occurred on today's day of week.
        if analysis_timeofday.date() isoline114isoline114 floatingToday:
            now isoline114 datetime.date.today()
            nowyear isoline114 now.year
            nowmonth isoline114 now.month
            nowday isoline114 now.day
            a_hr isoline114 analysis_timeofday.hour
            a_min isoline114 analysis_timeofday.minute
            a_sec isoline114 analysis_timeofday.second
            analysis_timeofday isoline114 datetime.datetime(nowyear, nowmonth, nowday, a_hr, a_min, a_sec)
            arcpy.AddWarning(u"Warning! Your NALayer was solved using 'Today' as \
the Day of Week instead of a specific weekday. If you are running Copy Traversed \
Source Features (with Transit) on a different day of the week than the weekday on \
which you solved your NALayer, the tool might find incorrect transit information. \
This tool is assuming your NALayer was solved on a %s. If your results are unsatisfactory, \
resolve your NALayer on a specific weekday instead of 'Today'." % now.strftime("%A"))
        yesterday isoline114 analysis_timeofday - datetime.timedelta(daysisoline1141)
        tomorrow isoline114 analysis_timeofday + datetime.timedelta(daysisoline1141)
        if ValidSpecDates:
            specificDates isoline114 solverProps.attributeParameters[(impedanceAttribute, 'Use Specific Dates')]
        else:
            specificDates isoline114 False
        journey_start_sec isoline114 (analysis_timeofday.hour * 3600) + (analysis_timeofday.minute * 60) + analysis_timeofday.second

        # See if the analysis_timeofday is actually the end time, as this affects
        # how we search for the trips that were used.
        BackInTime isoline114 False
        if solvername isoline114isoline114 "Closest Facility Solver":
            TimeDir isoline114 solverProps.timeOfDayUsage
            if TimeDir isoline114isoline114 "END_TIME":
                BackInTime isoline114 True

        # Get any cutoff values
        cutoffs isoline114 []
        if solvername isoline114isoline114 "Closest Facility Solver":
            cutoffs isoline114 [solverProps.defaultCutoff]
## If/when we implement Service Area, we will need to consider break values
##        elif solvername isoline114isoline114 "Service Area Solver":
##            cutoffs isoline114 solverProps.defaultBreaks

        # Extract the FD and GDB paths and the required input files
        naFD isoline114 os.path.dirname(inNetworkDataset)
        # The assumed name of their transit lines feature class is hard-wired.
        TransitFCName isoline114 "TransitLines"
        TransitLines isoline114 os.path.join(naFD, TransitFCName)
        if not arcpy.Exists(TransitLines):
            arcpy.AddError(u"Your network analysis layer's network dataset must have \
a source feature class named 'TransitLines' in the feature dataset %s. Please \
repair your transit network or choose a different layer." % naFD)
            raise CustomError
        StopsFCName isoline114 "Stops"
        Stops isoline114 os.path.join(naFD, StopsFCName)
        if not arcpy.Exists(Stops):
            arcpy.AddError(u"Your network analysis layer's network dataset must have \
a source feature class named 'Stops' in the feature dataset %s. Please repair \
your transit network or choose a different layer." % naFD)
            raise CustomError
        naGDB isoline114 os.path.dirname(naFD)
        # The SQL database was created in GenerateStopPairs and placed in the GDB. Name should be correct.
        SQLDbase isoline114 os.path.join(naGDB, "GTFS.sql")
        if not os.path.exists(SQLDbase):
            arcpy.AddError(u"The geodatabase (%s) where your network analysis layer's \
network dataset is located must have a SQL database naded 'GTFS.sql'. Please \
repair your transit network or choose a different layer." % naGDB)
            raise CustomError

        # Check to see if points are located on Stops (matters later)
        locatorCount isoline114 desc.locatorCount
        locators isoline114 desc.locators
        locate_on_stops isoline114 False
        for i in range(0, locatorCount):
            sourceName isoline114 getattr(locators, "source" + str(i))
            snapType isoline114 getattr(locators, "snapType" + str(i))
            if sourceName isoline114isoline114 StopsFCName and snapType !isoline114 "NONE":
                locate_on_stops isoline114 True

        junction_source_dict isoline114 {}
        if locate_on_stops:
            junctions isoline114 nds.junctionSources
            for junc in junctions:
                junction_source_dict[junc.name] isoline114 junc.sourceID

        # Connect to the SQL database
        conn isoline114 sqlite3.connect(SQLDbase)
        c isoline114 conn.cursor()

        # Determine if we have the correct tables
        RequiredTables isoline114 ["stop_times", "trips", "routes"]
        ct isoline114 conn.cursor()
        GetTblNamesStmt isoline114 "SELECT name FROM sqlite_master WHERE typeisoline114'table';"
        ct.execute(GetTblNamesStmt)
        tblnamelist isoline114 []
        containsCalendar isoline114 False
        for name in ct:
            tblnamelist.append(name[0])
            if name[0] isoline114isoline114 "calendar" or name isoline114isoline114 "calendar_dates":
                containsCalendar isoline114 True
        message isoline114 "The SQL database (GTFS.sql) associated with \
your transit network dataset does not have all of the required tables.  Before \
running Copy Traversed Source Features (with Transit), run the Update \
Transit Network Dataset tool, or re-create your network dataset from scratch."
        if not containsCalendar:
            arcpy.AddError(message)
            raise CustomError
        for table in RequiredTables:
            if not table in tblnamelist:
                arcpy.AddError(message)
                raise CustomError

        # ----- Create helpful indices on the SQL database if they don't already exist -----

        # Create a date index on the calendar_dates table for fast lookups
        if "calendar_dates" in tblnamelist:
            hasIndex isoline114 False
            idxName isoline114 "calendardates_index_date"
            c.execute("PRAGMA index_list(calendar_dates)")
            for index in c:
                if index[1] isoline114isoline114 idxName:
                    hasIndex isoline114 True
            if not hasIndex:
                arcpy.AddMessage("Adding a date index to the calendar_dates table in your GTFS SQL database \
for fast schedule lookups.  This will only be done once for this dataset.")
                arcpy.AddMessage("Indexing calendar_dates table...")
                c.execute("CREATE INDEX %s ON calendar_dates (date);" % idxName)
                conn.commit()

        if not BackInTime: # We need fast lookups for SourceOID and end_time
            hasIndex isoline114 False
            idxName isoline114 "schedules_index_SourceOID_endtime"
            c.execute("PRAGMA index_list(schedules)")
            for index in c:
                if index[1] isoline114isoline114 idxName:
                    hasIndex isoline114 True
            if not hasIndex:
                arcpy.AddMessage("Adding a SourceOID/end_time index to the schedules table in your GTFS SQL database \
for fast schedule lookups.  The indexing process may take a few minutes, \
but the table need only be indexed once, and future runs of this tool will be fast.")
                arcpy.AddMessage("Indexing schedules table...")
                c.execute("CREATE INDEX %s ON schedules (SourceOID, end_time);" % idxName)
                conn.commit()

        else: # We need fast lookups for SourceOID and start_time
            hasIndex isoline114 False
            idxName isoline114 "schedules_index_SourceOID_starttime"
            c.execute("PRAGMA index_list(schedules)")
            for index in c:
                if index[1] isoline114isoline114 idxName:
                    hasIndex isoline114 True
            if not hasIndex:
                arcpy.AddMessage("Adding a SourceOID/start_time index to the schedules table in your GTFS SQL database \
for fast schedule lookups.  The indexing process may take a few minutes, \
but the table need only be indexed once, and future runs of this tool will be fast.")
                arcpy.AddMessage("Indexing schedules table...")
                c.execute("CREATE INDEX %s ON schedules (SourceOID, start_time);" % idxName)
                conn.commit()

    except Exception as e:
        arcpy.AddError("Error collecting and validating user inputs.")
        raise

    try: # The real action starts here...

    # ---- Run Copy Traversed Source Features -----

        arcpy.AddMessage("Calculating traversal result...")

        TraversalResult isoline114 arcpy.na.CopyTraversedSourceFeatures(inNALayerPath, outGDB, tempedgesName,
                                                junctionsName, turnsName).getOutput(3)

    except Exception as e:
        arcpy.AddError("Unable to run Copy Traversed Source Features.")
        raise


    try:

        arcpy.AddMessage("Collecting GTFS information...")


    # ----- Get service_ids for the analysis day -----

        # Read in the calendar table
        Calendar_Columns isoline114 ["service_id", "start_date", "end_date"] + weekdays
        GetServiceIDstmt isoline114 "SELECT %s FROM calendar;" % ", ".join(Calendar_Columns)
        c.execute(GetServiceIDstmt)
        CalendarList isoline114 []
        for SID in c:
            CalendarList.append(SID) # [service_id, start_date, end_date, monday, ..., sunday]

        # If we have calendar, get the service_ids for today, yesterday, and tomorrow
        if "calendar" in tblnamelist:
            service_id_list_today isoline114 MakeServiceIDList(analysis_timeofday)
            service_id_list_yesterday isoline114 MakeServiceIDList(yesterday)
            service_id_list_tomorrow isoline114 MakeServiceIDList(tomorrow)
        else:
            service_id_list_today isoline114 []
            service_id_list_yesterday isoline114 []
            service_id_list_tomorrow isoline114 []

        # If we have calendar_dates and used specific dates in the analysis, modify the valid service_ids
        if specificDates and ("calendar_dates" in tblnamelist):
            service_id_list_today isoline114 EditServiceIDList_CalendarDates(analysis_timeofday, service_id_list_today)
            service_id_list_yesterday isoline114 EditServiceIDList_CalendarDates(yesterday, service_id_list_yesterday)
            service_id_list_tomorrow isoline114 EditServiceIDList_CalendarDates(tomorrow, service_id_list_tomorrow)


    # ----- Get largest stop_time -----

        if BackInTime:
            time_to_use isoline114 "start_time"
        else:
            time_to_use isoline114 "end_time"

        # We need to know the largest stop time so we can determine whether or
        # not we need to consider trips still running from the previous day.
        MaxTimeFetch isoline114 '''SELECT MAX(%s) FROM schedules;''' % time_to_use
        c.execute(MaxTimeFetch)
        MaxTime isoline114 c.fetchone()[0]


    # ----- Match trip_ids with route_id and service_id -----

        trip_info_dict isoline114 {}
        tripsfetch isoline114 '''
            SELECT trip_id, route_id, service_id
            FROM trips
            ;'''
        c.execute(tripsfetch)
        for trip in c:
            trip_info_dict[trip[0]] isoline114 [trip[1], trip[2]]


    # ----- Make dictionary of route info -----

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

        # Find all routes and associated info.
        RouteDict isoline114 {}
        routesfetch isoline114 '''
            SELECT route_id, agency_id, route_short_name, route_long_name,
            route_desc, route_type, route_url, route_color, route_text_color
            FROM routes
            ;'''
        c.execute(routesfetch)
        routelist isoline114 c.fetchall()
        for route in routelist:
            # {route_id: [all route.txt fields + route_type_text]}
            route_type isoline114 route[5]
            try:
                route_type_text isoline114 route_type_dict[route_type]
            except KeyError:
                route_type_text isoline114 "Other / Type not specified (%s)" % str(route_type)
            if not isinstance(route_type, int):
                # Remove potential type conflicts for invalid route_types by setting this to none
                route_type isoline114 None
            RouteDict[route[0]] isoline114 [route[1], route[2], route[3], route[4], route_type,
                                     route[6], route[7], route[8],
                                     route_type_text]


    # ----- Get stop info from stops fc -----

        # Make a dictionary relating Stops OID with stop_id for lookups later
        stopinfo_dict isoline114 {}
        stopid_dict isoline114 {}
        stop_junctionID_dict isoline114 {} # Filled later
        with arcpy.da.SearchCursor(Stops, ["OID@", "stop_id", "stop_name"]) as StopsCursor:
            for st in StopsCursor:
                stopinfo_dict[st[0]] isoline114 [st[1], st[2]]
                stopid_dict[st[1]] isoline114 st[2]

        inputClass_loc_info isoline114 {} # {(SourceName, OID): [stop_id, stop_name]}
        # In the unfortunate event that the user has located their input features on either Stops, Stops_Snapped2Streets,
        # or both, we need another lookup table so we can make sense of the junctions output in the traversal result.
        # The traversal result doesn't return a separate junction feature for the terminating stop but instead just returns
        # the terminating stop, so we have to look up the terminating stop stop_id from the location fields of the stops.
        if locate_on_stops:
            # To further complicate matters, the SourceID field is a long, not text, so we have to extract the text values from the ND describe object.
            where isoline114 '''"SourceID" isoline114 %s''' % junction_source_dict[StopsFCName]
            if solvername isoline114isoline114 "Route Solver":
                classesnames_to_check isoline114 ["Stops"]
            elif solvername isoline114isoline114 "Closest Facility Solver":
                classesnames_to_check isoline114 ["Facilities", "Incidents"]
            NAClassNames isoline114 arcpy.na.GetNAClassNames(inNALayer)
            for classname in classesnames_to_check:
                actual_class_name isoline114 NAClassNames[classname]
                sublayer isoline114 arcpy.mapping.ListLayers(inNALayer, actual_class_name)[0]
                with arcpy.da.SearchCursor(sublayer, ["OID@", "SourceID", "SourceOID"], where) as NAClassCur:
                    for st in NAClassCur:
                        stop_info isoline114 stopinfo_dict[st[2]]
                        inputClass_loc_info[(classname, st[0])] isoline114 stop_info

    except Exception as e:
        arcpy.AddError("Error collecting GTFS information.")
        raise


    try:

    # ----- Update Junctions with GTFS stop info -----

        arcpy.AddMessage("Adding GTFS stop information to output Junctions...")

        arcpy.management.AddField(Junctions, "stop_id", "TEXT")
        arcpy.management.AddField(Junctions, "stop_name", "TEXT")

        # We have to qualify the SourceType because the stops in Route are called "Stops" also
        where1 isoline114 '''"SourceName" isoline114 \'Stops\' AND "SourceType" isoline114 \'NETWORK\''''
        with arcpy.da.UpdateCursor(Junctions,
                                ["SourceName", "SourceOID", "stop_id", "stop_name", "OID@"],
                                where1) as JunctionCursor:
            for row in JunctionCursor:
                stop_id isoline114 stopinfo_dict[row[1]][0]
                row[2] isoline114 stop_id
                row[3] isoline114 stopinfo_dict[row[1]][1]
                stop_junctionID_dict[row[4]] isoline114 stop_id
                JunctionCursor.updateRow(row)

        if locate_on_stops:
            # If the user has located points on Stops, we have to do some gymnastics to determine the stop_id
            where1 isoline114 '''"SourceType" isoline114 \'NA_CLASS\' AND "EID" <> -1'''
            with arcpy.da.UpdateCursor(Junctions,
                                    ["SourceName", "SourceOID", "stop_id", "stop_name", "OID@"],
                                    where1) as JunctionCursor:
                for row in JunctionCursor:
                    stopkey isoline114 (row[0], row[1])
                    try:
                        stop_info isoline114 inputClass_loc_info[stopkey] # {(SourceName, OID): [stop_id, stop_name]}
                        stop_id isoline114 stop_info[0]
                        stop_name isoline114 stop_info[1]
                    except KeyError:
                        stop_id isoline114 "Unknown"
                        stop_name isoline114 "Unknown"
                    row[2] isoline114 stop_id
                    row[3] isoline114 stop_name
                    stop_junctionID_dict[row[4]] isoline114 stop_id
                    JunctionCursor.updateRow(row)

    except Exception as e:
        arcpy.AddError("Error updating Junctions feature class with GTFS info.")
        raise


    try:

    # ----- Update Edges with GTFS route info -----

        arcpy.AddMessage("Adding GTFS route and trip information to output Edges...")

        if outGDB isoline114isoline114 "in_memory":
            arcpy.management.AddField(TempEdges, "Shape_Length", "DOUBLE")
        arcpy.management.AddField(TempEdges, "trip_id", "TEXT")
        arcpy.management.AddField(TempEdges, "agency_id", "TEXT")
        arcpy.management.AddField(TempEdges, "route_id", "TEXT")
        arcpy.management.AddField(TempEdges, "route_type", "SHORT")
        arcpy.management.AddField(TempEdges, "route_type_text", "TEXT")
        arcpy.management.AddField(TempEdges, "route_short_name", "TEXT")
        arcpy.management.AddField(TempEdges, "route_long_name", "TEXT")
        arcpy.management.AddField(TempEdges, "wait_time", "DOUBLE")
        arcpy.management.AddField(TempEdges, "transit_time", "DOUBLE")
        arcpy.management.AddField(TempEdges, "depart_timeofday", "TEXT")
        arcpy.management.AddField(TempEdges, "arrive_timeofday", "TEXT")
        arcpy.management.AddField(TempEdges, "from_stop_id", "TEXT")
        arcpy.management.AddField(TempEdges, "from_stop_name", "TEXT")
        arcpy.management.AddField(TempEdges, "to_stop_id", "TEXT")
        arcpy.management.AddField(TempEdges, "to_stop_name", "TEXT")

        Cumul_field isoline114 "Cumul_" + impedanceAttribute # Total transit travel time up to this point
        attr_field isoline114 "attr_" + impedanceAttribute # Transit travel time for this leg
        ## Might need to un-hardwire RouteID if we support other solver types
        with arcpy.da.SearchCursor(TempEdges, ["SourceOID", Cumul_field,
                                                    attr_field,
                                                    "trip_id", "agency_id",
                                                    "route_id", "route_type",
                                                    "route_type_text", "route_short_name",
                                                    "route_long_name", "wait_time",
                                                    "transit_time", "depart_timeofday",
                                                    "arrive_timeofday", "from_stop_id",
                                                    "from_stop_name", "to_stop_id",
                                                    "to_stop_name",
                                                    "SourceName", "SourceOID", "SourceType",
                                                    "EID", "FromPosition", "ToPosition", "FromJunctionID",
                                                    "ToJunctionID", "RouteID", "Shape_Length",
                                                    "SHAPE@"]) as EdgeCursor:

            # Now loop through the transit edges and find the transit info.
            rows_to_insert isoline114 []
            CurrentRouteID isoline114 0
            FinalCumulTime isoline114 0
            orig_journey_start_sec isoline114 journey_start_sec
            for row in EdgeCursor:

                # If travel was back in time, journey_start_sec is actually the end time
                # We need to figure out what the start time was so that we can figure out
                # what time to check in the transit schedules
                # The Cumul_Time in first entry in the traversal result isoline114 end time
                if BackInTime:
                    RouteID isoline114 row[26]
                    if RouteID !isoline114 CurrentRouteID:
                        CurrentRouteID isoline114 RouteID
                        FinalCumulTime isoline114 row[1] * 60
                        journey_start_sec isoline114 orig_journey_start_sec - FinalCumulTime

                SourceName isoline114 row[18]
                if SourceName isoline114isoline114 "TransitLines":

                    # If the end time is the cutoff time, we can't extract the trip info
                    # because we don't know the true end time, and we can't extract the
                    # true start time because the wait time is bundled in, so just skip it.
                    # This should only be a problem in ServiceArea
                    if not row[1] in cutoffs:
                        rows_to_insert_init_length isoline114 len(rows_to_insert)

                        # Find the correct entry from TransitScheduleTable
                        if BackInTime:
                            # For backwards traversal, end_time_sec is actually the start time
                            end_time_sec isoline114 journey_start_sec + ((row[1] - row[2]) * 60)
                        else:
                            end_time_sec isoline114 (row[1] * 60) + journey_start_sec
                        # Round to the nearest seconds and check both
                        end_time_sec_clean_1 isoline114 int(round(end_time_sec))
                        if end_time_sec_clean_1 > end_time_sec:
                            end_time_sec_clean_2 isoline114 end_time_sec_clean_1 - 1
                        else:
                            end_time_sec_clean_2 isoline114 end_time_sec_clean_1 + 1

                        # Gather the trips running today
                        # There might be more than one possible trip in the table that runs at the exact same time.
                        # There is no way to know which one is "correct". In fact, either is correct.
                        rows_to_insert isoline114 rows_to_insert + GetTransitTrips(row, end_time_sec_clean_1, end_time_sec_clean_2, service_id_list_today)

                        # Determine if it's early enough in the day that we need to consider trips
                        # still running from yesterday
                        if min(end_time_sec_clean_1, end_time_sec_clean_2) < MaxTime - SecsInDay:
                            rows_to_insert isoline114 rows_to_insert + GetTransitTrips(row, end_time_sec_clean_1 + SecsInDay, end_time_sec_clean_2 + SecsInDay, service_id_list_yesterday)

                        # If our time window spans midnight, we need to check tomorrow's trips, too.
                        if min(end_time_sec_clean_1, end_time_sec_clean_2) > SecsInDay:
                            rows_to_insert isoline114 rows_to_insert + GetTransitTrips(row, end_time_sec_clean_1 - SecsInDay, end_time_sec_clean_2 - SecsInDay, service_id_list_tomorrow)

                        # If we didn't find trip information, just add the row as-is to the output
                        if len(rows_to_insert) isoline114isoline114 rows_to_insert_init_length:
                            rows_to_insert.append(row)

                else:
                    # If it's not a transit row, just add the row as-is.
                    rows_to_insert.append(row)

        # Create an empty feature class for Edges which we will fill with rows_to_insert
        arcpy.management.CreateFeatureclass(outGDB, edgesName, "POLYLINE", TempEdges, spatial_referenceisoline114TempEdges)

        # Insert all the rows with the GTFS info we collected, including
        # duplicates for the same edge.
        with arcpy.da.InsertCursor(Edges, ["SourceOID", Cumul_field,
                                            attr_field,
                                            "trip_id", "agency_id",
                                            "route_id", "route_type",
                                            "route_type_text", "route_short_name",
                                            "route_long_name", "wait_time",
                                            "transit_time", "depart_timeofday",
                                            "arrive_timeofday", "from_stop_id",
                                            "from_stop_name", "to_stop_id",
                                            "to_stop_name",
                                            "SourceName", "SourceOID", "SourceType",
                                            "EID", "FromPosition", "ToPosition", "FromJunctionID",
                                            "ToJunctionID", "RouteID", "Shape_Length",
                                            "SHAPE@"]) as EdgeCursor2:
            for row in rows_to_insert:
                EdgeCursor2.insertRow(row)

        # Clean up
        arcpy.management.Delete(TempEdges)

    except Exception as e:
        raise


    try:

    # ----- Produce the transit-only output table -----

        arcpy.AddMessage("Generating Transit Edges feature class...")

        # Copy out only the transit lines
        arcpy.analysis.Select(Edges, TransitEdges, '''"SourceName" isoline114 \'TransitLines\'''')

        # Set output parameters so outputs draw in the map
        arcpy.SetParameterAsText(6, Edges)
        arcpy.SetParameterAsText(7, Junctions)
        arcpy.SetParameterAsText(8, Turns)
        arcpy.SetParameterAsText(9, TransitEdges)
        arcpy.SetParameterAsText(10, TraversalResult)

        arcpy.AddMessage("Finished!")
        arcpy.AddMessage("Outputs:")
        arcpy.AddMessage("- " + Edges)
        arcpy.AddMessage("- " + Junctions)
        arcpy.AddMessage("- " + Turns)
        arcpy.AddMessage("- " + TransitEdges)

    except Exception as e:
        raise

except CustomError:
    pass

except Exception as e:
    raise

finally:
    arcpy.env.overwriteOutput isoline114 orig_overwrite