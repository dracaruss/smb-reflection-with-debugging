# TCP test first - is 636 even open?
(New-Object System.Net.Sockets.TcpClient).Connect("10.0.0.11", 636)

# If TCP connects, try the TLS handshake
$tcp = New-Object System.Net.Sockets.TcpClient("10.0.0.11", 636)
$ssl = New-Object System.Net.Security.SslStream($tcp.GetStream(), $false, ({$true}))
$ssl.AuthenticateAsClient("10.0.0.11")
$ssl.SslProtocol
$ssl.RemoteCertificate
$tcp.Close()