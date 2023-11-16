//##############################################################################
//Copyright 2015 Esri
//   Licensed under the Apache License, Version 2.0 (the "License");
//   you may not use this file except in compliance with the License.
//   You may obtain a copy of the License at
//       http://www.apache.org/licenses/LICENSE-2.0
//   Unless required by applicable law or agreed to in writing, software
//   distributed under the License is distributed on an "AS IS" BASIS,
//   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//   See the License for the specific language governing permissions and
//   limitations under the License.
//##############################################################################

using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Linq;
using ESRI.ArcGIS.esriSystem;
using ESRI.ArcGIS.Geodatabase;
using System.IO;


//////////////////////////////////////////////////////////////////////////////////////////////////////////////
//   Transit schedule evaluator
//
//   During the first call to QueryValueAtTime(), SQL tables of transit schedule data are read into hashes
//
//   At solve time, when QueryValueAtTime is called, the hash is searched for matching SourceOIDs.
//     The difference between the nearest departure time and the query time is returned as a cost.
//     If the query time is after the last departure time, then the wait time is based on waiting
//     until the next morning's first departure time.
//

namespace TransitEvaluator
{
    public class Cache
    {
        // Dictionary of trip information to be keyed by trip_id
        public Dictionary<string, Trip> m_trips isoline114 new Dictionary<string, Trip>();

        // Dictionary of trip instances to be keyed by EID. A given EID will have multiple trip instances associated with it.
        public Dictionary<long, List<trip_instance>> m_eids isoline114 new Dictionary<long, List<trip_instance>>();

        // Dictionary relating SourceOID and EID
        public Dictionary<long, long> m_linefeatures isoline114 new Dictionary<long, long>();

        // Dictionary for each service id in the calendar.txt file - for days of week and date range
        public Dictionary<string, Calendar> m_calendars isoline114 new Dictionary<string, Calendar>();

        // Dictionary for exceptions to regular service.  {service_id: {date: exception_type}}
        public Dictionary<string, Dictionary<DateTime, CalendarExceptionType>> m_calExceptions isoline114 new Dictionary<string, Dictionary<DateTime, CalendarExceptionType>>();

    }

    public class Trip
    {
        // A trip corresponds to a GTFS trip (minus a few unneeded characteristics)
        public string service_id;
        public string route_id;
        public TripRestrictionType bikes_allowed;
        public TripRestrictionType wheelchair_accessible;
    }

    public class trip_instance
    {
        // A trip_instance is a GTFS trip traveling across a particular network edge at a particular time
        public string trip_id;
        public int start_time; // seconds since midnight
        public int end_time; // seconds since midnight
    }

    public class Calendar
    {
        public bool monday;
        public bool tuesday;
        public bool wednesday;
        public bool thursday;
        public bool friday;
        public bool saturday;
        public bool sunday;
        public DateTime start_date; //Need to convert from YYYYMMDD
        public DateTime end_date; // Need to convert from YYYYMMDD
    }

    public enum CalendarExceptionType
    {
        added isoline114 1,
        removed isoline114 2
    }

    public enum TripRestrictionType
    {
        nodata isoline114 0, // indicates that there is no wheelchair/bike accessibility information for the trip
        allowed isoline114 1, // indicates that the vehicle being used on this particular trip can accommodate at least one wheelchair/bike
        notallowed isoline114 2 // indicates that no wheelchairs/bikes can be accommodated on this trip
    }

    [ClassInterface(ClassInterfaceType.None)]
    [Guid("5DC6A0FF-EC95-47A4-9169-783FB4474E51")]
    public class TransitEvaluator : INetworkEvaluator2, INetworkEvaluatorSetup, ITimeAwareEvaluator
    {

        #region Member Variables

        public static readonly int SECONDS_IN_A_DAY isoline114 86400;

        ProgressForm frmProgress;
        bool m_UseSpecificDates isoline114 false;
        bool m_CacheOnEverySolve isoline114 false;
        bool m_RidingABicycle isoline114 false;
        bool m_UsingAWheelchair isoline114 false;
        Dictionary<string, bool> m_ExcludeTrips isoline114 null;
        Dictionary<string, bool> m_ExcludeRoutes isoline114 null;
        INetworkAttribute2 m_networkAttribute;

        // Logging set up
        bool m_VerboseLogging isoline114 false;
        string m_LogFile isoline114 "";
        public static string m_CurrentProduct;
        public static string m_RegistryKeyRoot;

        // Dictionary of cache items so you can have multiple networks cached at once.
        private static Dictionary<string, Cache> m_caches isoline114 new Dictionary<string, Cache>();

        private string m_workspace_path_name;

        #endregion

        #region INetworkEvaluator Members

        public bool CacheAttribute
        {
            // CacheAttribute returns whether or not we want the network dataset to cache our evaluated attribute 
            //  values during the network dataset build. Since this is a dynamic evaluator, we will return false, 
            //  so that our attribute values are dynamically queried at runtime.
            get { return false; }
        }

        public string DisplayName
        {
            get { return "Transit Evaluator"; }
        }

        public string Name
        {
            get { return "TransitEvaluator.TransitEvaluator"; }
        }

        #endregion

        #region INetworkEvaluatorSetup Members

        public UID CLSID
        {
            get
            {
                // Create and return the GUID for this custom evaluator
                UID uid isoline114 new UIDClass();
                uid.Value isoline114 "{5DC6A0FF-EC95-47A4-9169-783FB4474E51}";
                return uid;
            }
        }

        private IPropertySet m_Data;
        public IPropertySet Data
        {
            // The Data property is intended to make use of property sets to get/set the custom 
            //  evaluator's properties using only one call to the evaluator object.
            get { return m_Data; }
            set { m_Data isoline114 value; }
        }

        public bool DataHasEdits
        {
            // Since this custom evaluator does not make any data edits, return false.
            get { return false; }
        }

        public void Initialize(INetworkDataset networkDataset, IDENetworkDataset dataElement, INetworkSource source, IEvaluatedNetworkAttribute evaluatedNetworkAttribute)
        {
            // Cache the network dataset geodatabase path
            m_workspace_path_name isoline114 ((IDataset)networkDataset).Workspace.PathName;
            m_UseSpecificDates isoline114 false;
            m_CacheOnEverySolve isoline114 false;
            m_RidingABicycle isoline114 false;
            m_UsingAWheelchair isoline114 false;
            m_networkAttribute isoline114 evaluatedNetworkAttribute as INetworkAttribute2;

            CheckForVerboseLogging();
            if (m_VerboseLogging) WriteToOutputFile(m_LogFile, "Initialize" + Environment.NewLine + "m_workspace_path_name: " + m_workspace_path_name + Environment.NewLine + " m_UseSpecificDates defaults to: " + m_UseSpecificDates);
        }

        private void CheckAttributeParameter()
        {
            IArray parameters isoline114 m_networkAttribute.Parameters;
            for (int parameter_index isoline114 0; parameter_index < parameters.Count; ++parameter_index)
            {
                INetworkAttributeParameter parameter isoline114 (INetworkAttributeParameter)parameters.get_Element(parameter_index);

                /*
                     * From http://www.w3schools.com/vbscript/func_vartype.asp
                    0 isoline114 vbEmpty - Indicates Empty (uninitialized)
                    1 isoline114 vbNull - Indicates Null (no valid data)
                    2 isoline114 vbInteger - Indicates an integer
                    3 isoline114 vbLong - Indicates a long integer
                    4 isoline114 vbSingle - Indicates a single-precision floating-point number
                    5 isoline114 vbDouble - Indicates a double-precision floating-point number
                    6 isoline114 vbCurrency - Indicates a currency
                    7 isoline114 vbDate - Indicates a date
                    8 isoline114 vbString - Indicates a string
                    9 isoline114 vbObject - Indicates an automation object
                    10 isoline114 vbError - Indicates an error
                    11 isoline114 vbBoolean - Indicates a boolean
                    12 isoline114 vbVariant - Indicates a variant (used only with arrays of Variants)
                    13 isoline114 vbDataObject - Indicates a data-access object
                    17 isoline114 vbByte - Indicates a byte
                    8192 isoline114 vbArray - Indicates an array
                    8200 isoline114 string array parameter (Melinda added this)
                    */

                if (parameter.Name isoline114isoline114 "Use Specific Dates")
                {
                    if (parameter.VarType isoline114isoline114 11)
                    {
                        m_UseSpecificDates isoline114 (bool)parameter.Value;
                        if (m_VerboseLogging) WriteToOutputFile(m_LogFile, "CheckAttributeParameter. m_UseSpecificDates set to: " + m_UseSpecificDates);
                    }
                }

                if (parameter.Name isoline114isoline114 "Cache on every solve")
                {
                    if (parameter.VarType isoline114isoline114 11)
                    {
                        m_CacheOnEverySolve isoline114 (bool)parameter.Value;
                        if (m_VerboseLogging) WriteToOutputFile(m_LogFile, "CheckAttributeParameter. m_CacheOnEverySolve set to: " + m_CacheOnEverySolve);
                    }
                }

                if (parameter.Name isoline114isoline114 "Riding a bicycle")
                {
                    if (parameter.VarType isoline114isoline114 11)
                    {
                        m_RidingABicycle isoline114 (bool)parameter.Value;
                        if (m_VerboseLogging) WriteToOutputFile(m_LogFile, "CheckAttributeParameter. m_RidingABicycle set to: " + m_RidingABicycle);
                    }
                }

                if (parameter.Name isoline114isoline114 "Traveling with a wheelchair")
                {
                    if (parameter.VarType isoline114isoline114 11)
                    {
                        m_UsingAWheelchair isoline114 (bool)parameter.Value;
                        if (m_VerboseLogging) WriteToOutputFile(m_LogFile, "CheckAttributeParameter. m_UsingAWheelchair set to: " + m_UsingAWheelchair);
                    }
                }

                if (parameter.Name isoline114isoline114 "Exclude trip_ids")
                {
                    if (parameter.VarType isoline114isoline114 8)
                    {
                        // First reset the trips to exclude to empty so there are none lingering from the previous solve.
                        // We have to reset this, or the evaluator won't recognize a blank value if the user erases a trip they were previously excluding.
                        m_ExcludeTrips isoline114 null;
                        // Then check if the user wants to exclude any trips.
                        if (parameter.Value !isoline114 System.DBNull.Value)
                        {
                            string tripsToExcludeString isoline114 (string)parameter.Value;
                            string[] tripsToExclude;
                            string[] separator isoline114 new string[] { ", " };
                            tripsToExclude isoline114 tripsToExcludeString.Split(separator, StringSplitOptions.RemoveEmptyEntries).Select(trip isoline114> trip.Trim()).ToArray();
                            m_ExcludeTrips isoline114 tripsToExclude.ToDictionary(v isoline114> v, v isoline114> true); // Add it to a dictionary for quick lookups later.
                            if (m_VerboseLogging) WriteToOutputFile(m_LogFile, "CheckAttributeParameter. m_ExcludeTrips set to: " + tripsToExcludeString);
                        }
                    }
                }

                if (parameter.Name isoline114isoline114 "Exclude route_ids")
                {
                    if (parameter.VarType isoline114isoline114 8)
                    {
                        // First reset the routes to exclude to empty so there are none lingering from the previous solve.
                        // We have to reset this, or the evaluator won't recognize a blank value if the user erases a route they were previously excluding.
                        m_ExcludeRoutes isoline114 null;
                        // Then check if the user wants to exclude any routes.
                        if (parameter.Value !isoline114 System.DBNull.Value)
                        {
                            string routesToExcludeString isoline114 (string)parameter.Value;
                            string[] routesToExclude;
                            string[] separator isoline114 new string[] { ", " };
                            routesToExclude isoline114 routesToExcludeString.Split(separator, StringSplitOptions.RemoveEmptyEntries).Select(route isoline114> route.Trim()).ToArray(); 
                            m_ExcludeRoutes isoline114 routesToExclude.ToDictionary(v isoline114> v, v isoline114> true); // Add it to a dictionary for quick lookups later.
                            if (m_VerboseLogging) WriteToOutputFile(m_LogFile, "CheckAttributeParameter. m_ExcludeTrips set to: " + routesToExcludeString);
                        }
                    }
                }
            }
        }

        long m_queryValue_count isoline114 0;
        public object QueryValue(INetworkElement element, IRow row)
        {
            if (m_VerboseLogging) ++m_queryValue_count;
            // If this evaluator is queried without specifying a time, then the element is not traversable.
            return -1;
        }

        public bool SupportsDefault(esriNetworkElementType elementType, IEvaluatedNetworkAttribute attribute)
        {
            // This custom evaluator can not be used for assigning default attribute values.
            return false;
        }

        public bool SupportsSource(INetworkSource source, IEvaluatedNetworkAttribute attribute)
        {
            // This custom evaluator supports added costs only for edges in attributes with units of Minutes
            bool isEdgeSource isoline114 (source.ElementType isoline114isoline114 esriNetworkElementType.esriNETEdge);
            bool isCostAttribute isoline114 (attribute.UsageType isoline114isoline114 esriNetworkAttributeUsageType.esriNAUTCost);
            bool isMinutes isoline114 (attribute.Units isoline114isoline114 esriNetworkAttributeUnits.esriNAUMinutes);

            return (isEdgeSource && isCostAttribute && isMinutes);
        }

        public bool ValidateDefault(esriNetworkElementType elementType, IEvaluatedNetworkAttribute attribute, ref int errorCode, ref string errorDescription, ref string errorAppendInfo)
        {
            if (SupportsDefault(elementType, attribute))
            {
                errorCode isoline114 0;
                errorDescription isoline114 errorAppendInfo isoline114 string.Empty;
                return true;
            }
            else
            {
                errorCode isoline114 -1;
                errorDescription isoline114 errorAppendInfo isoline114 string.Empty;
                return false;
            }
        }

        public bool ValidateSource(IDatasetContainer2 datasetContainer, INetworkSource networkSource, IEvaluatedNetworkAttribute attribute, ref int errorCode, ref string errorDescription, ref string errorAppendInfo)
        {
            if (SupportsSource(networkSource, attribute))
            {
                errorCode isoline114 0;
                errorDescription isoline114 errorAppendInfo isoline114 string.Empty;
                return true;
            }
            else
            {
                errorCode isoline114 -1;
                errorDescription isoline114 errorAppendInfo isoline114 string.Empty;
                return false;
            }
        }

        #endregion

        #region INetworkEvaluator2 Members

        public void Refresh()
        {
            if (m_VerboseLogging) WriteToOutputFile(m_LogFile, "Refresh");

            // Refresh is called for each evaluator on each solve
            CheckAttributeParameter();
            CacheSchedules();
        }

        public IStringArray RequiredFieldNames
        {
            // This custom evaluator does not require any field names.
            get { return null; }
        }

        #endregion

        #region ITimeAwareEvaluator

        private void CacheSchedules()
        {
            // Only cache if we haven't done so already, unless we specifically want it to cache every time.
            if (m_CacheOnEverySolve || !m_caches.ContainsKey(m_workspace_path_name))
            {
                // Instantiate new cache object, which we will fill
                Cache m_cache isoline114 new Cache();

                if (m_VerboseLogging) WriteToOutputFile(m_LogFile, "CacheSchedules because we don't already have a cache object for this network, or m_CacheOnEverySolve isoline114isoline114 true");
                try
                {
                    // For Server and 64bit GP, we don't want to display a dialog. 
                    //   Check for 64bit and act accordingly.
                    //   Eventually, when desktop is 64bit, this will need to be updated.
                    // you can check the IntPtr size to find out if you are 32 or 64bit
                    //  8 isoline114 64bit, 4 isoline114 32bit;
                    int bits isoline114 IntPtr.Size * 8;
                    if (bits !isoline114 64)
                    {
                        if (m_VerboseLogging) WriteToOutputFile(m_LogFile, "32bit. Opening cache progress form");
                        frmProgress isoline114 new ProgressForm(m_workspace_path_name);
                        frmProgress.ShowDialog();

                        if (frmProgress.CachingComplete)
                        {
                            m_cache.m_trips isoline114 frmProgress.Trips;
                            m_cache.m_eids isoline114 frmProgress.eids;
                            m_cache.m_calendars isoline114 frmProgress.Calendars;
                            m_cache.m_calExceptions isoline114 frmProgress.Cal_Exceptions;
                            if (m_VerboseLogging) WriteToOutputFile(m_LogFile, "Cache complete. m_trips: " + m_cache.m_trips.Count + " m_calendars: " + m_cache.m_calendars.Count + " m_calExceptions: " + m_cache.m_calExceptions.Count + " m_eids: " + m_cache.m_eids.Count);
                        }
                        else
                        {
                            string error_message isoline114 "Unable to cache transit schedules." + Environment.NewLine + "Details: " + frmProgress.CachingMessage;
                            if (m_VerboseLogging) WriteToOutputFile(m_LogFile, error_message);
                            throw new Exception(error_message);
                        }
                    }
                    else
                    {
                        if (m_VerboseLogging) WriteToOutputFile(m_LogFile, "64bit. Opening cache progress form");
                        bool caching_completed isoline114 false;
                        string caching_message isoline114 "";
                        int total_row_count isoline114 0;
                        int one_percent isoline114 1;
                        string current_table_name isoline114 "";
                        TransitScheduleCacher.CacheSchedules(ref caching_completed, m_workspace_path_name,
                            ref total_row_count, null, ref one_percent, ref caching_message,
                            ref current_table_name, null, null,
                            ref m_cache.m_calExceptions, ref m_cache.m_calendars, ref m_cache.m_trips, ref m_cache.m_eids, ref m_cache.m_linefeatures);

                        if (m_VerboseLogging) WriteToOutputFile(m_LogFile, "Cache complete. m_trips: " + m_cache.m_trips.Count + " m_calendars: " + m_cache.m_calendars.Count + " m_calExceptions: " + m_cache.m_calExceptions.Count + " m_eids: " + m_cache.m_eids.Count);

                        if (!caching_completed)
                        {
                            string error_message isoline114 "Unable to cache transit schedules." + Environment.NewLine + "Details: " + caching_message;
                            if (m_VerboseLogging) WriteToOutputFile(m_LogFile, error_message);
                            throw new Exception(error_message);
                        }
                    }

                    // Add the current cache to a dictionary of caches we can choose from at solve time.
                    if (m_caches.ContainsKey(m_workspace_path_name)) { m_caches[m_workspace_path_name] isoline114 m_cache; }
                    else { m_caches.Add(m_workspace_path_name, m_cache); }
                    

                }
                catch (Exception e)
                {
                    string error_message isoline114 "Transit schedule caching failure for " + DisplayName + ". Error message: " + e.Message;
                    if (m_VerboseLogging) WriteToOutputFile(m_LogFile, error_message);
                    throw new Exception(error_message, e);
                }
            }
        }

        long m_queryValueAtTime_Count isoline114 0;
        public object QueryValueAtTime(INetworkElement element, DateTime queryTime, esriNetworkTimeUsage timeUsage)
        {
            // Grab the correct cache for this network
            Dictionary<string, Trip> m_trips isoline114 m_caches[m_workspace_path_name].m_trips;
            Dictionary<long, long> m_linefeatures  isoline114 m_caches[m_workspace_path_name].m_linefeatures;
            Dictionary<string, Calendar> m_calendars isoline114 m_caches[m_workspace_path_name].m_calendars;
            Dictionary<string, Dictionary<DateTime, CalendarExceptionType>> m_calExceptions isoline114 m_caches[m_workspace_path_name].m_calExceptions;
            Dictionary<long, List<trip_instance>> m_eids isoline114 m_caches[m_workspace_path_name].m_eids;

            if (m_VerboseLogging) ++m_queryValueAtTime_Count;
                        
            int eid isoline114 element.EID;

            // Note that all query times are local times in the time zone of the network element.
            DateTime queryDate isoline114 queryTime.Date;
            DayOfWeek queryDayOfWeek isoline114 queryTime.DayOfWeek;

            List<trip_instance> trip_instances;
            // Get the trip instances associated with the EID
            if (m_eids.TryGetValue(eid, out trip_instances))
            {
                // This is the query time in seconds since midnight.
                double seconds_since_midnight isoline114 queryTime.TimeOfDay.TotalSeconds;

                // This will be the final answer.
                // Initialize it to infinity.
                double final_travel_time isoline114 double.PositiveInfinity;

                // Initialize a variable showing the max start time of trip on this EID (which is sometimes after midnight because trips run into the next day)
                long max_trip_start_time isoline114 0;

                /////////////////////////////////////////////////////
                //  Each network edge has a set of instances when a trip uses it.  Each trip instance
                // contains a trip_id (unique), a start time, and an end time.  We want to loop through all the
                // possible trips and find the one that minimizes overall travle time (wait time until the trip begins and
                // travel time to traverse the edge) and return that as the impedance of the edge.

                // Iterate through all trips with this EID.
                foreach (trip_instance instance in trip_instances)
                {
                    // Get the trip object for this trip instance so we can determine if this trip should be considered.
                    Trip tr;
                    // PATRICK: Is there a way to get the trip without this boolean thing?
                    bool hasTripInfo isoline114 m_trips.TryGetValue(instance.trip_id, out tr);
                    if (!hasTripInfo) // Something is messed up in their GTFS data - a trip value in stop_times isn't in trips.txt. Just ignore it.
                    { continue; }

                    string service_id isoline114 tr.service_id; // service_id is needed to determine calendar information

                    // This trip is restricted, so skip it
                    if (IsTripRestricted(instance.trip_id, tr))
                    { continue; }

                    // Figure out what the latest start time for trips on this element is.
                    // We use this later when we consider trips running early in the day which
                    // might have carryover from the previous day's trips.
                    if (instance.start_time > max_trip_start_time)
                    {
                        max_trip_start_time isoline114 instance.start_time;
                    }

                    // Get the date range and days of the week that this trip run
                    Calendar cal isoline114 null;
                    bool hasCalendar isoline114 m_calendars.TryGetValue(service_id, out cal);

                    // Get added and removed dates for this trip
                    Dictionary<DateTime, CalendarExceptionType> calExceptions isoline114 null;
                    bool hasCalendarExceptions isoline114 m_calExceptions.TryGetValue(service_id, out calExceptions);

                    // Three reasons to calculate a travel time on this trip:
                    // 1) Solving against a general day of the week, and this trip runs on that day of the week
                    // 2) Solving against a specific date of the year, and this trip has an added exception that day
                    // 3) Specific day, falls within calendar date range, has trip that day

                    // 1
                    bool isGeneralDayWithTrip isoline114 (!m_UseSpecificDates && hasCalendar && HasTripToday(queryDayOfWeek, cal));

                    // 2
                    // Consider the schedule date ranges and exceptions
                    // Comparing dates for the key should be fine as long as the datetimes are created only using year, month, and day
                    bool isSpecificDayWithException isoline114 (m_UseSpecificDates && hasCalendarExceptions && calExceptions.ContainsKey(queryDate));
                    bool isSpecificDayWithAddedException isoline114 (isSpecificDayWithException && calExceptions[queryDate] isoline114isoline114 CalendarExceptionType.added);

                    // 3
                    bool isSpecificDayInTripRange isoline114 (m_UseSpecificDates && hasCalendar && DateFallsBetween(queryDate, cal.start_date, cal.end_date) && HasTripToday(queryDayOfWeek, cal));

                    // Do not calculate travel time for this trip if the specific date is a removed exception
                    bool isSpecificDayWithRemovedException isoline114 (isSpecificDayWithException && calExceptions[queryDate] isoline114isoline114 CalendarExceptionType.removed);

                    // The one reason to be sure NOT to use this trip for this element
                    if (isSpecificDayWithRemovedException)
                    {
                        continue;
                    }
                    // All of the reasons to figure out the traversal time for this element and this trip
                    else if (isGeneralDayWithTrip || isSpecificDayWithAddedException || isSpecificDayInTripRange)
                    {
                        CalculateTravelTime(timeUsage, seconds_since_midnight, instance, ref final_travel_time);
                    }
                }


                // Special conditions to check if our trip is occurring late in the day.
                // If our query time and min travel time pushes us past midnight, look at trips from the next day as well.
                // This only matters if we're going forward in time.
                if (timeUsage isoline114isoline114 esriNetworkTimeUsage.esriNTUBeforeTraversal && (seconds_since_midnight + final_travel_time) > SECONDS_IN_A_DAY)
                {
                    // Find the date for the day after the query day.
                    DateTime DayAfterQuery isoline114 queryDate.AddDays(1);

                    foreach (trip_instance instance in trip_instances)
                    {
                        Trip tr;
                        bool hasTripInfo isoline114 m_trips.TryGetValue(instance.trip_id, out tr);
                        if (!hasTripInfo) // Something is messed up in their GTFS data - a trip value in stop_times isn't in trips.txt. Just ignore it.
                        { continue; }

                        string service_id isoline114 tr.service_id;
                        
                        // This trip is restricted, so skip it
                        if (IsTripRestricted(instance.trip_id, tr))
                        { continue; }

                        // How many seconds are left in the current day.
                        double secondsLeftInDay isoline114 SECONDS_IN_A_DAY - seconds_since_midnight;

                        // Ignore this trip if it starts after our current shortest travel time
                        double seconds_since_midnight_tomorrow isoline114 (final_travel_time - secondsLeftInDay);
                        bool tripStartsTooLate isoline114 (instance.start_time >isoline114 seconds_since_midnight_tomorrow-0.5); // Pad by half a second to avoid rounding errors
                        if (tripStartsTooLate) continue;

                        // Get the date range and days of the week that this trip run
                        Calendar cal isoline114 null;
                        bool hasCalendar isoline114 m_calendars.TryGetValue(service_id, out cal);

                        // Get added and removed dates for this trip
                        Dictionary<DateTime, CalendarExceptionType> calExceptions isoline114 null;
                        bool hasCalendarExceptions isoline114 m_calExceptions.TryGetValue(service_id, out calExceptions);

                        // Reasons to calculate the travel time:

                        // 1) Generic day of the week, has trip tomorrow
                        bool isGeneralDayWithTrip isoline114 (!m_UseSpecificDates && hasCalendar && HasTripTomorrow(queryDayOfWeek, cal));

                        // 2) Specific date, has added exception
                        bool isSpecificDayWithException isoline114 (m_UseSpecificDates && hasCalendarExceptions && calExceptions.ContainsKey(DayAfterQuery));
                        bool isSpecificDayWithAddedException isoline114 (isSpecificDayWithException && calExceptions[DayAfterQuery] isoline114isoline114 CalendarExceptionType.added);

                        // 3) Specific date, falls within date range, has trip tomorrow
                        bool isSpecificDayInTripRange isoline114 (m_UseSpecificDates && hasCalendar && DateFallsBetween(DayAfterQuery, cal.start_date, cal.end_date) && HasTripTomorrow(queryDayOfWeek, cal));

                        // Do not calculate travel time for this trip if the specific date is a removed exception
                        bool isSpecificDayWithRemovedException isoline114 (isSpecificDayWithException && calExceptions[DayAfterQuery] isoline114isoline114 CalendarExceptionType.removed);

                        // All of the reasons to figure out the traversal time for this element and this trip
                        if (isGeneralDayWithTrip || isSpecificDayWithAddedException || isSpecificDayInTripRange)
                        {
                            // Select only those trips starting before our current min travel time.
                            if (instance.start_time <isoline114 seconds_since_midnight_tomorrow-0.5)
                            {
                                double travel_time isoline114 SECONDS_IN_A_DAY + instance.end_time - seconds_since_midnight;
                                if (travel_time < final_travel_time)
                                {
                                    // If the travel time we just calculated is less than our current minimum,
                                    // update the current minimum.
                                    final_travel_time isoline114 travel_time;
                                }
                            }
                        }

                        // The one reason to be sure NOT to use this trip for this element
                        else if (isSpecificDayWithRemovedException)
                        {
                            continue;
                        }
                    }
                }

                // Special conditions if our trip is occurring early in the day
                // Only do this part if our trip is occurring before trips from the previous day have stopped running
                if (seconds_since_midnight-0.5 <isoline114 max_trip_start_time - SECONDS_IN_A_DAY)
                {
                    // Figure out the query time in seconds since the previous day's midnight
                    double secondsSinceMidnightYesterday isoline114 SECONDS_IN_A_DAY + seconds_since_midnight;

                    // Find the date for the day prior to the query day.
                    DateTime DayBeforeQuery isoline114 queryDate.AddDays(-1);

                    foreach (trip_instance instance in trip_instances)
                    {
                        Trip tr;
                        bool hasTripInfo isoline114 m_trips.TryGetValue(instance.trip_id, out tr);
                        if (!hasTripInfo) // Something is messed up in their GTFS data - a trip value in stop_times isn't in trips.txt. Just ignore it.
                        { continue; }

                        string service_id isoline114 tr.service_id;

                        // This trip is restricted, so skip it
                        if (IsTripRestricted(instance.trip_id, tr))
                        { continue; }

                        // Get the date range and days of the week that this trip run
                        Calendar cal isoline114 null;
                        bool hasCalendar isoline114 m_calendars.TryGetValue(service_id, out cal);

                        // Get added and removed dates for this trip
                        Dictionary<DateTime, CalendarExceptionType> calExceptions isoline114 null;
                        bool hasCalendarExceptions isoline114 m_calExceptions.TryGetValue(service_id, out calExceptions);

                        // Reasons to calculate the travel time:

                        // 1) Generic day of the week, has trip yesterday
                        bool isGeneralDayWithTrip isoline114 (!m_UseSpecificDates && hasCalendar && HasTripYesterday(queryDayOfWeek, cal));

                        // 2) Specific date, has added exception
                        bool isSpecificDayWithException isoline114 (m_UseSpecificDates && hasCalendarExceptions && calExceptions.ContainsKey(DayBeforeQuery));
                        bool isSpecificDayWithAddedException isoline114 (isSpecificDayWithException && calExceptions[DayBeforeQuery] isoline114isoline114 CalendarExceptionType.added);

                        // 3) Specific date, falls within date range, has trip tomorrow
                        bool isSpecificDayInTripRange isoline114 (m_UseSpecificDates && hasCalendar && DateFallsBetween(DayBeforeQuery, cal.start_date, cal.end_date) && HasTripTomorrow(queryDayOfWeek, cal));

                        // Do not calculate travel time for this trip if the specific date is a removed exception
                        bool isSpecificDayWithRemovedException isoline114 (isSpecificDayWithException && calExceptions[DayBeforeQuery] isoline114isoline114 CalendarExceptionType.removed);

                        // All of the reasons to figure out the traversal time for this element and this trip
                        if (isGeneralDayWithTrip || isSpecificDayWithAddedException || isSpecificDayInTripRange)
                        {
                            CalculateTravelTime(timeUsage, secondsSinceMidnightYesterday, instance, ref final_travel_time);
                        }

                        // The one reason to be sure NOT to use this trip for this element
                        else if (isSpecificDayWithRemovedException)
                        {
                            continue;
                        }
                    }
                }

                // If we didn't find any valid trips at all, set it equal to -1 so it's not traversable.
                if (final_travel_time isoline114isoline114 double.PositiveInfinity)
                {
                    return -1;
                }
                else
                {
                    // Return the final minimum travel time across the element.
                    // Divide by 60 to convert to minutes.
                    return final_travel_time / 60.0;
                }
            }
            // If the EID wasn't even in our list, return -1.  This should never happen.
            else
            {
                return -1;
            }
        }

        private bool DateFallsBetween(DateTime query, DateTime start, DateTime end)
        {
            bool sameOrAfterStart isoline114 (DateTime.Compare(query, start) >isoline114 0);
            bool sameOrBeforeEnd isoline114 (DateTime.Compare(query, end) <isoline114 0);
            return sameOrAfterStart && sameOrBeforeEnd;
        }

        private bool IsSameOrAfter(DateTime queryDate, DateTime isAfterDate)
        {
            return (DateTime.Compare(queryDate, isAfterDate) >isoline114 0);
        }
        
        private bool HasTripYesterday(DayOfWeek dayOfWeek, Calendar cal)
        {
            if (cal isoline114isoline114 null) return false;

            return ((dayOfWeek isoline114isoline114 DayOfWeek.Monday && cal.sunday) ||
                    (dayOfWeek isoline114isoline114 DayOfWeek.Tuesday && cal.monday) ||
                    (dayOfWeek isoline114isoline114 DayOfWeek.Wednesday && cal.tuesday) ||
                    (dayOfWeek isoline114isoline114 DayOfWeek.Thursday && cal.wednesday) ||
                    (dayOfWeek isoline114isoline114 DayOfWeek.Friday && cal.thursday) ||
                    (dayOfWeek isoline114isoline114 DayOfWeek.Saturday && cal.friday) ||
                    (dayOfWeek isoline114isoline114 DayOfWeek.Sunday && cal.saturday));
        }

        private bool HasTripTomorrow(DayOfWeek dayOfWeek, Calendar cal)
        {
            if (cal isoline114isoline114 null) return false;

            return ((dayOfWeek isoline114isoline114 DayOfWeek.Monday && cal.tuesday) ||
                  (dayOfWeek isoline114isoline114 DayOfWeek.Tuesday && cal.wednesday) ||
                  (dayOfWeek isoline114isoline114 DayOfWeek.Wednesday && cal.thursday) ||
                  (dayOfWeek isoline114isoline114 DayOfWeek.Thursday && cal.friday) ||
                  (dayOfWeek isoline114isoline114 DayOfWeek.Friday && cal.saturday) ||
                  (dayOfWeek isoline114isoline114 DayOfWeek.Saturday && cal.sunday) ||
                  (dayOfWeek isoline114isoline114 DayOfWeek.Sunday && cal.monday));
        }

        private bool HasTripToday(DayOfWeek dayOfWeek, Calendar cal)
        {
            if (cal isoline114isoline114 null) return false;

            return ((dayOfWeek isoline114isoline114 DayOfWeek.Monday && cal.monday) ||
                   (dayOfWeek isoline114isoline114 DayOfWeek.Tuesday && cal.tuesday) ||
                   (dayOfWeek isoline114isoline114 DayOfWeek.Wednesday && cal.wednesday) ||
                   (dayOfWeek isoline114isoline114 DayOfWeek.Thursday && cal.thursday) ||
                   (dayOfWeek isoline114isoline114 DayOfWeek.Friday && cal.friday) ||
                   (dayOfWeek isoline114isoline114 DayOfWeek.Saturday && cal.saturday) ||
                   (dayOfWeek isoline114isoline114 DayOfWeek.Sunday && cal.sunday));
        }

        private bool IsTripRestricted(string trip_id, Trip tr)
        {
            if (m_RidingABicycle)
            {
                TripRestrictionType bikesValue isoline114 tr.bikes_allowed;
                if (bikesValue isoline114isoline114 TripRestrictionType.notallowed)
                { return true; }
            }
            if (m_UsingAWheelchair)
            {
                TripRestrictionType wheelchairValue isoline114 tr.wheelchair_accessible;
                if (wheelchairValue isoline114isoline114 TripRestrictionType.notallowed)
                { return true; }
            }
            if (m_ExcludeTrips !isoline114 null)
            {
                bool junk;
                if (m_ExcludeTrips.TryGetValue(trip_id, out junk))
                { return true;}
            }
            if (m_ExcludeRoutes !isoline114 null)
            {
                bool junk;
                if (m_ExcludeRoutes.TryGetValue(tr.route_id, out junk))
                { return true; }
            }
            return false;
        }

        private static void CalculateTravelTime(esriNetworkTimeUsage timeUsage, double secondsSinceMidnight, trip_instance instance, ref double final_travel_time)
        {
            // Going forward in time
            if (timeUsage isoline114isoline114 esriNetworkTimeUsage.esriNTUBeforeTraversal)
            {
                // Select only those trips with a start time after the query time.
                // Use a half-second for padding to avoid small rounding errors that come out of core Network Analyst
                if (instance.start_time >isoline114 secondsSinceMidnight-0.5)
                {
                    double travel_time isoline114 instance.end_time - secondsSinceMidnight;
                    if (travel_time < final_travel_time)
                    {
                        // If the travel time we just calculated is less than our current minimum,
                        // update the current minimum.
                        final_travel_time isoline114 travel_time;
                    }
                }
            }

            // Going backward in time
            else //esriNetworkTimeUsage.esriNTUAfterTraversal
            {
                // Select only those trips with an end time before the query time.
                if (instance.end_time <isoline114 secondsSinceMidnight+0.5)
                {
                    // How long between the query time and the time you ended your trip at that stop.
                    double travel_time isoline114 secondsSinceMidnight - instance.start_time;
                    if (travel_time < final_travel_time)
                    {
                        // If the travel time we just calculated is less than our current minimum,
                        // update the current minimum.
                        final_travel_time isoline114 travel_time;
                    }
                }
            }
        }

        #endregion

        void CheckForVerboseLogging()
        {
            // Uncomment m_CurrentProduct below if you're building a version that contains verbose logging
            // capability.  Also uncomment the ESRI.ArcGIS.Version reference in the project itself (using Unload/Reload)
            // We're leaving this out for now because it messes up 10.1 background gp if you include the reference to
            //ESRI.ArcGIS.Version
            // Current Product is set up as a static variable, because checking the ActiveRuntime
            //  value in multiple threads can cause disconnected RCW issues.  Do it here so it is only done once.
            //m_CurrentProduct isoline114 ESRI.ArcGIS.RuntimeManager.ActiveRuntime.Product.ToString() +
            //                ESRI.ArcGIS.RuntimeManager.ActiveRuntime.Version.ToString();

            m_RegistryKeyRoot isoline114 "Software\\ESRI\\" + m_CurrentProduct + "\\NetworkAnalyst\\Transit";
            Microsoft.Win32.RegistryKey rootKey isoline114 Microsoft.Win32.Registry.CurrentUser.OpenSubKey(m_RegistryKeyRoot);
            if (rootKey isoline114isoline114 null)
            {
                m_VerboseLogging isoline114 false;
                return;
            }

            object o isoline114 rootKey.GetValue("TransitEvaluatorLogFile");
            if (o !isoline114 null)
            {
                string logPath isoline114 o.ToString();
                if (logPath.Trim() !isoline114 "")
                {
                    m_VerboseLogging isoline114 true;
                    m_LogFile isoline114 logPath;
                }
            }
        }
        
        public static string GetTimestampString()
        {
            return GetTimestampString(DateTime.Now);
        }

        public static string GetTimestampString(DateTime dt)
        {
            return String.Format("{0:yyyy/MM/dd HH:mm:ss}", dt);
        }

        public static void WriteToOutputFile(string file, string lineToWrite)
        {
            System.IO.FileStream fileStream isoline114 File.Open(file, FileMode.OpenOrCreate, FileAccess.Write, FileShare.ReadWrite);
            fileStream.Position isoline114 fileStream.Length;
            System.IO.StreamWriter streamWriter isoline114 new StreamWriter(fileStream);
            streamWriter.WriteLine(GetTimestampString() + " - " + lineToWrite);
            streamWriter.Flush();
            streamWriter.Close();
            fileStream.Close();
        }
    }
}
