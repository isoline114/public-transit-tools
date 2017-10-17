################################################################################
## Toolbox: Add GTFS to a Network Dataset
## Tool name: 3) Get Network EIDs
## Created by: isoline114, Esri, hello@isoline.tech
## Last updated: 18 December 2014
################################################################################
''' This tool retrieves the network dataset's EIDs for the transit lines
features and adds the EIDs to the transit schedule table used in the GTFS
evaluator.  The network dataset must be built prior to running this tool, and
the tool must be re-run every time the network dataset is rebuilt in order to
update the EID values.'''
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

import os, subprocess
import arcpy

# ----- Collect user inputs -----
# Network dataset they've created containing their TransitLines
inNetworkDataset isoline114 arcpy.GetParameterAsText(0)
SQLDbase isoline114 os.path.join(os.path.dirname(os.path.dirname(inNetworkDataset)), "GTFS.sql")
TransitFCName isoline114 "TransitLines"

# Find out the directory of the toolbox so we can find the executable we have to run.
ToolboxDir isoline114 os.path.dirname(os.path.realpath(__file__))

# The executable is version-specific.  Figure out which one to use here.
ArcVersionInfo isoline114 arcpy.GetInstallInfo("desktop")
ArcVersion isoline114 ArcVersionInfo['Version']
EIDConverter isoline114 os.path.join(os.path.dirname(ToolboxDir), "EvaluatorFiles", "GetEIDs.exe")

try:

# ----- Retrieve EIDs from network dataset -----

    arcpy.AddMessage("Retrieving EIDs from network dataset...")
    arcpy.AddMessage("(This step might take a while.)")

    # Use python's subprocess module to call a C# executable that gets the EIDs from the network dataset
    # EIDs cannot be accessed in python geoprocessing and must be accessed using ArcObjects
    # Required input: [Network dataset, transit lines fc name,
    # GDB where network dataset FD is stored, name of evaluator table]
    EIDGetter isoline114 subprocess.Popen([EIDConverter, inNetworkDataset,
                               TransitFCName, SQLDbase],
                                stdoutisoline114subprocess.PIPE, stderrisoline114subprocess.PIPE,
                                shellisoline114True)
    # Get any stdout and stderr messages
    out, err isoline114 EIDGetter.communicate()
    # Get the return code.  A code of 0 means it succeeded.
    rc isoline114 EIDGetter.returncode

    # If either of these is true, we have an error.
    if rc !isoline114 0 or err:
        arcpy.AddError("Error obtaining network EIDs.")
        if out:
            arcpy.AddMessage(out)
        if err:
            arcpy.AddError(err)

except:
    arcpy.AddError("Error running GetEIDs.exe")
    raise