#!powershell

#AnsibleRequires -CSharpUtil Ansible.Basic

$spec = @{
    options = @{
        state=@{ default="present"; choices="present", "absent" }

    }
}

$module = [Ansible.Basic.AnsibleModule]::Create($args, $spec)
$state = $module.Params.state

$zuul_console = @'
$listener = New-Object System.Net.Sockets.TcpListener("0.0.0.0", 19885)
$listener.Start()
[console]::WriteLine("Listening on :19885")
while ($true) {
    $client = $listener.AcceptTcpClient()
    [console]::WriteLine("{0} >> Accepted Client " -f (Get-Date).ToString())
    $newRunspace = [RunSpaceFactory]::CreateRunspace()
    $newRunspace.Open()
    $newRunspace.SessionStateProxy.setVariable("client", $client)
    $newPowerShell = [PowerShell]::Create()
    $newPowerShell.RunSpace = $newRunspace
    $process = {
        $client.close()
    }
    $jobHandle = $newPowerShell.AddScript($process).BeginInvoke()
}
'@
$zuul_console | Out-File -FilePath .\zuul_console.ps1

try {
    $port = Get-NetTCPConnection -LocalPort 19885 -ErrorAction Stop
    if ($state -eq "absent") {
        (Get-Process -Id $port.OwningProcess).Kill()
        $module.Result.changed = $true
    }
} catch [Microsoft.PowerShell.Cmdletization.Cim.CimJobException] {
    if ($state -eq "present") {
        Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList "powershell.exe $home\zuul_console.ps1"
        $module.Result.changed = $true
    }
}

$module.ExitJson()
