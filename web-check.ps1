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
            "$($r.StatusCode) ${scheme}://${host_}"
        } catch {
            $code = $_.Exception.Response.StatusCode.value__
            if ($code) {
                "$code ${scheme}://${host_}"
            } else {
                "ERR ${scheme}://${host_} - $($_.Exception.Message)"
            }
        }
    }
}
