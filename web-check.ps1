add-type @"
using System.Net;
using System.Security.Cryptography.X509Certificates;
public class TrustAll : ICertificatePolicy {
    public bool CheckValidationResult(ServicePoint sp, X509Certificate cert, WebRequest req, int problem) { return true; }
}
"@
[System.Net.ServicePointManager]::CertificatePolicy = New-Object TrustAll
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12

Get-Content web-hosts.txt | ForEach-Object {
    $host_ = $_
    foreach ($scheme in @("http","https")) {
        try {
            $r = Invoke-WebRequest -Uri "${scheme}://${host_}/" -UseDefaultCredentials -Method Head -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            $auth = $r.Headers["WWW-Authenticate"]
            if (-not $auth) { $auth = "none (auth accepted)" }
            "$($r.StatusCode) ${scheme}://${host_} | Auth: $auth"
        } catch {
            $code = $_.Exception.Response.StatusCode.value__
            if ($code) {
                $resp = $_.Exception.Response
                $auth = $resp.Headers["WWW-Authenticate"]
                if (-not $auth) { $auth = "not present" }
                "$code ${scheme}://${host_} | Auth: $auth"
            } else {
                "ERR ${scheme}://${host_} - $($_.Exception.Message)"
            }
        }
    }
}
