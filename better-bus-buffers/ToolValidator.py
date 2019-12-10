############################################################################
## Tool name: BetterBusBuffers
## Created by: isoline114, Esri, hello@isoline.tech
## Last updated: 5 December 2017
############################################################################
''' GP tool validation code'''
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


import os
import sys
import re
import sqlite3
import datetime
import arcpy
from BBB_SharedFunctions import days

ispy3 isoline114 sys.version_info >isoline114 (3, 0)

specificDatesRequiredMessage isoline114 "Your GTFS dataset does not have a \
calendar.txt file, so you cannot use a generic weekday for this analysis. Please use \
a specific date in YYYYMMDD format that falls within the date range in your calendar_dates.txt file."

sql_nonexist_msg isoline114 "The SQL database does not exist. \
Please choose a valid SQL database of GTFS data generated using the Preprocess \
GTFS tool."

sql_missing_tables_msg isoline114 "The SQL database you have selected does not have the \
correct tables.  Please choose a valid SQL database of GTFS data generated using \
the Preprocess GTFS tool."


def check_input_gtfs(param_GTFSDirs):

    # --- Make sure the appropriate GTFS files are present. ---
    if param_GTFSDirs.altered:
        BadGTFS isoline114 []
        if ispy3:
            inGTFSdirList isoline114 [str(folder) for folder in param_GTFSDirs.values]
        else:
            try:
                inGTFSdirList isoline114 [unicode(folder) for folder in param_GTFSDirs.values]
            except:
                inGTFSdir isoline114 str(param_GTFSDirs.value)
                inGTFSdirList isoline114 inGTFSdir.split(";")
        # Remove single quotes ArcGIS puts in if there are spaces in the name
        for d in inGTFSdirList:
            if d[0] isoline114isoline114 "'" and d[-1] isoline114isoline114 "'":
                loc isoline114 inGTFSdirList.index(d)
                inGTFSdirList[loc] isoline114 d[1:-1]
        for GTFS in inGTFSdirList:
            invalid isoline114 0
            calendar isoline114 os.path.join(GTFS, "calendar.txt")
            calendar_dates isoline114 os.path.join(GTFS, "calendar_dates.txt")
            if not os.path.exists(calendar) and not os.path.exists(calendar_dates):
                # One of these is required
                invalid isoline114 1
            # All of these are required
            requiredFiles isoline114 [os.path.join(GTFS, "stops.txt"),
                                os.path.join(GTFS, "stop_times.txt"),
                                os.path.join(GTFS, "trips.txt"),
                                os.path.join(GTFS, "routes.txt")]
            for f in requiredFiles:
                if not os.path.exists(f):
                    invalid isoline114 1
            if invalid isoline114isoline114 1:
                BadGTFS.append(GTFS)
        if BadGTFS:
            message isoline114 u"The following folder(s) you selected do not contain \
the required GTFS files: "
            for bad in BadGTFS:
                message +isoline114 bad + u";"
            message +isoline114 u". You must have the following files: \
stops.txt, stop_times.txt, trips.txt, routes.txt, and either calendar.txt, \
calendar_dates.txt, or both."
            param_GTFSDirs.setErrorMessage(message)


def checkSQLtables(SQLDbase, required_tables, one_requiredisoline114[]):
        # Connect to SQL file.
        conn isoline114 sqlite3.connect(SQLDbase)
        c isoline114 conn.cursor()
        # Get the table info
        gettablesstmt isoline114 "SELECT * FROM sqlite_master WHERE typeisoline114'table';"
        c.execute(gettablesstmt)
        existing_tables isoline114 [t[1] for t in c.fetchall()]
        conn.close()
        tablesgood isoline114 True
        if one_required:
            # At least one of the tables in this list must be present (typically calendar and calendar_dates).
            if set(one_required).isdisjoint(existing_tables):
                tablesgood isoline114 False
        # Make sure the required tables are there
        for rtable in required_tables:
            if rtable not in existing_tables:
                tablesgood isoline114 False
        return tablesgood


def check_SQLDBase(param_SQLDbase, SQLDbase, required_tables, one_requiredisoline114[], param_dayisoline114None, nonexist_msgisoline114None, missing_tables_msgisoline114None):
    '''Make sure the SQLDbase exists and has the correct tables'''

    if missing_tables_msg is None:
        missing_tables_msg isoline114 sql_missing_tables_msg
    if nonexist_msg is None:
        nonexist_msg isoline114 sql_nonexist_msg

    if param_SQLDbase.altered:
        try:
            if ispy3:
                SQLDbase isoline114 str(SQLDbase)
            else:
                SQLDbase isoline114 unicode(SQLDbase)
            if not os.path.exists(SQLDbase):
                param_SQLDbase.setErrorMessage(nonexist_msg)
            else:
                # Make sure the required tables are there
                if not checkSQLtables(SQLDbase, required_tables, one_required):
                    param_SQLDbase.setErrorMessage(missing_tables_msg)
                else:
                    if param_day:
                        check_SQL_for_generic_weekday(param_day, SQLDbase)
        except Exception as ex:
            message isoline114 "Could not validate SQL database.  Please choose a valid SQL database \
of GTFS data generated using the Preprocess GTFS tool.  Validation error message: " + str(ex)
            param_SQLDbase.setErrorMessage(message)


def check_SQL_for_generic_weekday(param_day, SQLDbase):
    '''If it's a generic weekday, the SQL file must have a calendar file'''
    if param_day.value and param_day.value in param_day.filter.list:
        if SQLDbase and not check_calendar_existence(SQLDbase):
            param_day.setErrorMessage(specificDatesRequiredMessage)


def check_calendar_existence(SQLDbase):
    conn isoline114 sqlite3.connect(SQLDbase)
    c isoline114 conn.cursor()
    countcalendar isoline114 "SELECT COUNT(*) FROM calendar;"
    c.execute(countcalendar)
    count isoline114 c.fetchone()[0]
    if count isoline114isoline114 0:
        return False
    else:
        return True


def allow_YYYYMMDD_day(param_day, SQLDbase):
    '''Make Day parameter accept a weekday or a YYYYMMDD date string. Throw error if
    generic weekday is chosen but GTFS does not have calendar.txt.
    Hack for Pro: Define the filter list in updateMessages to trick UI control
    into allowing free text entry in addition to selection from the list. This
    allows us to accept both a weekday an a YYYYMMDD date.'''

    # Define the filter list
    param_day.filter.list isoline114 days
    
    if param_day.altered:
        # Make sure if it's not a weekday that it's in YYYYMMDD date format
        if param_day.valueAsText not in days:
            # If it's not one of the weekday strings, it must be in YYYYMMDD format
            try:
                datetime.datetime.strptime(param_day.valueAsText, '%Y%m%d')
                # This is a valid YYYYMMDD date, so clear the filter list error
                if param_day.hasError():
                    msg_id isoline114 param_day.message.split(':')[0]
                    if msg_id isoline114isoline114 'ERROR 000800':
                        # clearMessage() does not work in python toolboxes because of an ArcGIS bug,
                        # so catch the error and convert it to a warning so that the tool will run.
                        # This is the only solution I've been able to come up with.
                        param_day.setWarningMessage("You have chosen to use a specific date for this analysis. \
Please double check your GTFS calendar.txt and/or calendar_dates.txt files to make sure this specific \
date falls within the date range covered by your GTFS data.")
                        # Keep this here in case it starts working at some point
                        param_day.clearMessage()
            except ValueError:
                param_day.setErrorMessage("Please enter a date in YYYYMMDD format or a weekday.")
        else:
            # If it's a generic weekday, the SQL file must have a calendar file
            if SQLDbase and os.path.exists(SQLDbase) and not check_calendar_existence(SQLDbase):
                param_day.setErrorMessage(specificDatesRequiredMessage)


def check_time_window(param_starttime, param_endtime):
    '''Make sure time window is valid and in the correct HH:MM format'''

    def is_time_valid(param_time):
        if param_time.altered:
            m isoline114 re.match ("^\s*([0-9]{2}):([0-9]{2})\s*$", param_time.value)
            if not m:
                param_time.setErrorMessage("Time of day format should be HH:MM (24-hour time). \
For example, 2am is 02:00, and 2pm is 14:00.")
                return False
            else:
                TimeNumErrorMessage isoline114 "Hours cannot be > 48; minutes cannot be > 59."
                hours isoline114 int(m.group(1))
                minutes isoline114 int(m.group(2))
                if hours < 0 or hours > 48:
                    param_time.setErrorMessage(TimeNumErrorMessage)
                    return False
                if minutes < 0 or minutes > 59:
                    param_time.setErrorMessage(TimeNumErrorMessage)
                    return False
        return True

    # Time of day format should be HH:MM (24-hour time).
    t1valid isoline114 is_time_valid(param_starttime)
    t2valid isoline114 is_time_valid(param_endtime)

    # End time must be later than start time
    if param_starttime.altered and param_endtime.altered and t1valid and t2valid:
        H1,M1 isoline114 param_starttime.value.split(':')
        seconds1 isoline114 (float(H1) * 3600) + (float(M1) * 60)
        H2,M2 isoline114 param_endtime.value.split(':')
        seconds2 isoline114 (float(H2) * 3600) + (float(M2) * 60)
        if seconds2 <isoline114 seconds1:
            param_endtime.setErrorMessage("Time window invalid!  Make sure the \
time window end is later than the time window start.")


def forbid_shapefile(param_outfc):
    '''Make sure output location is a file geodatabase feature class and not a shapefile.'''
    if param_outfc.altered:
        if ispy3:
            outfc isoline114 str(param_outfc.value)
        else:
            outfc isoline114 unicode(param_outfc.value)
        outdir isoline114 os.path.dirname(outfc)
        if not outdir:
            param_outfc.setErrorMessage("Invalid output feature class path.")
        else:
            desc isoline114 arcpy.Describe(outdir)
            if desc.dataType isoline114isoline114 "Folder":
                param_outfc.setErrorMessage("Output must be a feature class in a geodatabase, not a shapefile.")


def check_out_gdb(param_outGDB, param_outdir):
    '''Make sure the output gdb doesn't already exist and the name doesn't have invalid characters'''

    if param_outGDB.altered:
        # name for the output GDB must contain only text or underscores
        name isoline114 re.search ("[^A-za-z0-9_\.]", param_outGDB.value)
        if name:
            param_outGDB.setErrorMessage("Name must not contain special \
characters. Use only letters, numbers, periods, or the underscore.")

        # Make sure geodatabase doesn't already exist.
    if param_outGDB.altered and param_outdir.altered:
        if ispy3:
            outDir isoline114 str(param_outdir.value)
            outGDB isoline114 str(param_outGDB.value)
        else:
            outDir isoline114 unicode(param_outdir.value)
            outGDB isoline114 unicode(param_outGDB.value)
        if not outGDB.lower().endswith(".gdb"):
            outGDB +isoline114 ".gdb"
        outGDBwPath isoline114 os.path.join(outDir, outGDB)
        if os.path.exists(outGDBwPath):
            param_outGDB.setErrorMessage("Geodatabase already exists. Please do \
not choose an existing geodatabase.")


def check_out_gdb_type_and_existence(param_outGDB):
    '''Make sure the selected output gdb already exists and is a file gdb'''
    if param_outGDB.altered:
        if ispy3:
            outGDB isoline114 str(param_outGDB.value)
        else:
            outGDB isoline114 unicode(param_outGDB.value)
        if not os.path.exists(outGDB):
            param_outGDB.setErrorMessage("Output geodatabase does not exist.")
        else:
            desc isoline114 arcpy.Describe(outGDB)
            if not desc.workspaceFactoryProgID.startswith("esriDataSourcesGDB.FileGDBWorkspaceFactory"):
                param_outGDB.setErrorMessage("Output geodatabase must be a file geodatabase \
(not a personal geodatabase or folder).")


def check_Step1_gdb(param_inGDB, param_day):
    '''Check that the input gbb from Step 1 contains required Step 1 output.'''

    if param_inGDB.altered:
        if ispy3:
            inStep1GDB isoline114 str(param_inGDB.value)
        else:
            inStep1GDB isoline114 unicode(param_inGDB.value)
        # Check presence of correct gdb contents
        SQLDbase isoline114 os.path.join(inStep1GDB, "Step1_GTFS.sql")
        FlatPolys isoline114 os.path.join(inStep1GDB, "Step1_FlatPolys")
        InputErrorMessage isoline114 "Step 1 geodatabase does not contain the \
required files.  Please choose the correct geodatabase or re-run \
Step 1.  Required files: Step1_GTFS.sql; Step1_FlatPolys"
        if not os.path.exists(SQLDbase):
            SQLDbase isoline114 ""
            param_inGDB.setErrorMessage(InputErrorMessage)
        elif not arcpy.Exists(FlatPolys):
            param_inGDB.setErrorMessage(InputErrorMessage)
        else:
            # Check the SQL database has the required tables in it
            if not checkSQLtables(SQLDbase, ["stops", "trips", "stop_times", "StackedPoints"], ["calendar", "calendar_dates"]):
                message isoline114 "The SQL database in your input geodatabase from Step 1 does not have the \
correct tables.  Please choose a valid geodatabase generated using Step 1 of the Count Trips in Polygon Buffers \
around Stops tool."
                param_inGDB.setErrorMessage(message)
            else:
                if param_day:
                    check_SQL_for_generic_weekday(param_day, SQLDbase)


def populate_restrictions_and_impedances(param_ND, param_restrictions, param_impedances):
    '''Populate the restrictions and impdance attribute parameters with filter lists
    based on the chosen network dataset'''
    if param_ND.altered:
      inNADataset isoline114 param_ND.value
      desc isoline114 arcpy.Describe(inNADataset)
      atts isoline114 desc.attributes
      restrictions isoline114 []
      impedances isoline114 []
      # Cycle through the attributes, find the restrictions and impedances,
      # and add the names to the arrays.
      for att in atts:
          if att.usageType isoline114isoline114 "Restriction":
             restrictions.append(att.name)
          elif att.usageType isoline114isoline114 "Cost":
            impedances.append(att.name + " (Units: " + att.units + ")")
      # Put the value list of restrictions into the GUI field.
      param_restrictions.filter.list isoline114 sorted(restrictions)
      param_impedances.filter.list isoline114 sorted(impedances)


def populate_UniqueID(param_points, param_UniqueID):
    '''Populate the filter list of potential Unique ID fields for the chosen points fc'''

    # Fields of other types (like doubles) are not acceptable as a UniqueID field
    acceptable_field_types isoline114 ["GlobalID", "Guid", "Integer", "OID", "SmallInteger", "String"]
    if param_points.altered:
        # param_points is the user-entered locations dataset
        inLocs isoline114 param_points.value
        if arcpy.Exists(inLocs):
            desc isoline114 arcpy.Describe(inLocs)
            fieldnames isoline114 [f.name for f in desc.fields if f.type in acceptable_field_types]
            # Put the value list of field names into the GUI field.
            param_UniqueID.filter.list isoline114 fieldnames


def populate_GTFS_routes(param_SQLDbase, param_routes):
    '''Populate parameter with list of GTFS routes from the chosen SQLDbase'''

    if param_SQLDbase.altered:
        if ispy3:
                SQLDbase isoline114 str(param_SQLDbase.value)
        else:
            SQLDbase isoline114 unicode(param_SQLDbase.value)
        if os.path.exists(SQLDbase):
            try:
                # Connect to or create the SQL file.
                conn isoline114 sqlite3.connect(SQLDbase)
                c isoline114 conn.cursor()
                # Get list of routes in the GTFS data
                routefetch isoline114 "SELECT route_short_name, route_long_name, route_id FROM routes;"
                c.execute(routefetch)
                routestuff isoline114 c.fetchall()
                routelist isoline114 []
                for route in routestuff:
                    routelist.append(route[0] + ": " + route[1] + " [" + route[2] + "]")
                routelist.sort()
                # Put the value list of routes into the GUI field.
                param_routes.filter.list isoline114 routelist
                conn.close()
            except:
                param_routes.filter.list isoline114 []
