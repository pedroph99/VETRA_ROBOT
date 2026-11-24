from pathlib import Path
from coppeliasim_zmqremoteapi_client import RemoteAPIClient
from robot.greenhouse_scene import Scene, png_rgb
from server.src.config import PROJECT_ROOT
s=RemoteAPIClient().require('sim')
view=s.createVisionSensor(1|2|4|128,[1000,760,0,0],[.05,60,1.05,.01,0,0,.88,.9,.87,0,0])
a=Scene.__new__(Scene); a.sim=s
try:
    a.point_camera(view,[10,-12,12],[0,0,.2])
    s.handleVisionSensor(view)
    data,res=s.getVisionSensorImg(view)
    (PROJECT_ROOT/'robot'/'previews'/'estufa-preview.png').write_bytes(png_rgb(data,*res))
finally:
    s.removeObjects([view])
