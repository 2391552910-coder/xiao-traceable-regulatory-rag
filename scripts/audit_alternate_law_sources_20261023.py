Process terminated.
Exception of type 'System.OutOfMemoryException' was thrown.
   at System.Environment.FailFast(System.Runtime.CompilerServices.StackCrawlMarkHandle, System.String, System.Runtime.CompilerServices.ObjectHandleOnStack, System.String)
   at System.Environment.FailFast(System.Threading.StackCrawlMark ByRef, System.String, System.Exception, System.String)
   at System.Environment.FailFast(System.String, System.Exception)
   at Microsoft.PowerShell.UnmanagedPSEntry.Start(System.String[], Int32)
   at Microsoft.PowerShell.ManagedPSEntry.Main(System.String[])
System.OutOfMemoryException: Exception of type 'System.OutOfMemoryException' was thrown.
   at System.HexConverter.TryDecodeFrom_Vector128[TChar](ReadOnlySpan`1 source, Span`1 destination, Int32& elementsProcessed)
   at System.HexConverter.TryDecodeFrom_Vector128[TChar](ReadOnlySpan`1 source, Span`1 destination, Int32& elementsProcessed)
   at System.Reflection.AssemblyNameParser.TryParsePKT(String attributeValue, Boolean isToken, Byte[]& result)
   at System.Reflection.AssemblyNameParser.TryParse(AssemblyNameParts& result)
   at System.Reflection.AssemblyNameParser.Parse(ReadOnlySpan`1 name)
   at System.Reflection.AssemblyName..ctor(String assemblyName)
   at System.Management.Automation.Runspaces.PSSnapInHelpers.LoadPSSnapInAssembly(PSSnapInInfo psSnapInInfo)
   at System.Management.Automation.Runspaces.InitialSessionState.ImportPSSnapIn(PSSnapInInfo psSnapInInfo, PSSnapInException& warning)
   at System.Management.Automation.Runspaces.InitialSessionState.CreateDefault2()
   at Microsoft.PowerShell.UnmanagedPSEntry.Start(String[] args, Int32 argc)