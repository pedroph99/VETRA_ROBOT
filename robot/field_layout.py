"""Shared geometry for the scene, mission and dashboard (metres)."""
import math

HOME = (-1.9, -5.1)
STOP = (1.9, -5.1)
STRAIGHT = 9.3
RADIUS = 1.9
LENGTH = 2*STRAIGHT + math.pi*RADIUS


def route_point(distance):
    d = max(0., min(LENGTH, distance))
    if d >= LENGTH:
        return STOP
    if d <= STRAIGHT:
        return HOME[0], HOME[1]+d
    if d < STRAIGHT+math.pi*RADIUS:
        a = math.pi-(d-STRAIGHT)/RADIUS
        return RADIUS*math.cos(a), 4.2+RADIUS*math.sin(a)
    return STOP[0], 4.2-(d-STRAIGHT-math.pi*RADIUS)


ROUTE = [route_point(LENGTH*i/240) for i in range(241)]


def bed_layout():
    beds = []
    for i in range(12):
        row = i//2 if i < 8 else i-8
        x = (-3.8 if i%2 == 0 else 0.) if i < 8 else 3.8
        y = -3.6+row*2.4
        distance = y-HOME[1] if i < 8 else STRAIGHT+math.pi*RADIUS+4.2-y
        beds.append(dict(x=x, y=y, route_distance=distance))
    return beds
