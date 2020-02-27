Installation
------------

First, install docker into your system. Read about it here: https://www.docker.io/gettingstarted/

Then just do something like this, to launch a proxy for Torrent-TV:

1. Build the image.
   ```
   docker build -t dank100/aceproxy git@github.com:dank100/docker-acestream-proxy.git
   ```

2. Run the TorrentTV proxy with your key.
   ```
   docker run -d -t -p 8000:8000 dank100/aceproxy
   ```

3. Read AceProxy manual for usage instructions: https://github.com/ValdikSS/aceproxy/wiki.
   
   Or for the simple case of trying to load another acesteam link with the format 
   `acestream://{channel_id}` you can use the following link:
   
   ```
   http://[SERVER_IP]:8000/pid/{channel_id}/{channel_name}.mp4
   ```
   
   This works as a stream in VLC or other media players.