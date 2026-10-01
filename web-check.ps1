Get-Content web-hosts.txt | ForEach-Object {
    try {
        $r = Invoke-WebRequest -Uri "http://$_/" -UseDefaultCredentials -Method Head -UseBasicParsing -ErrorAction Stop
        "$($r.StatusCode) $_"
    } catch {
        "$($_.Exception.Response.StatusCode.value__) $_"
    }
}
