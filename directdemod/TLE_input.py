import numpy

def getSHIFT():
    # the tle consists of 70 columns#

    list1 = input()
    list2 = input()

    line1 = list(str(list1))
    line2 = list(str(list2))

    # mean motion of the satellite tells us its angular velocity in it's orbit #
    # but this isn't instantaneous velocity, it'a average over the whole day #
    # mean motion of a satellite is defined from array elements 53 to 63 in line2 #

    angular_velocity = ''
    i = 53

    while i<64:
        angular_velocity[i] = angular_velocity + line2[i]
        i=i+1

    velocity_of_cubesat = int(angular_velocity)*R)

    # R is the radius of the earth #

    doppler_shift = (C/(C-velocity_of_cubesat))*F

    # C is the speed of light #
    # F is the constant radio frequency used #
    # taking assumption that this is instantaneous velocity #


