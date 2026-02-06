Get-ScheduledTask | Where-Object {$_.TaskName -match 'AI|selector|trader'} |
    Select-Object TaskName, State, @{Name='Hidden';Expression={$_.Settings.Hidden}} |
    Format-Table -AutoSize
