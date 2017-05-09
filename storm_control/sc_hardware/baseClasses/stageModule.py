#!/usr/bin/env python
"""
Base class / functionality for controlling a motorized stage.

Hazen 04/17
"""

from PyQt5 import QtCore

import storm_control.hal4000.halLib.halMessage as halMessage

import storm_control.sc_hardware.baseClasses.hardwareModule as hardwareModule
import storm_control.sc_library.parameters as params


class StageFunctionality(hardwareModule.BufferedFunctionality):
    isMoving = QtCore.pyqtSignal(bool)
    stagePosition = QtCore.pyqtSignal(dict)

    def __init__(self, stage = None, update_interval = None, is_slow = False, **kwds):
        """
        stage - A hardware object that behaves like a stage.

        is_slow - Some stages are particularly slow, they only run at 9600 baud
                  for example. In that case it is probably best not to try and
                  use them for things like screen drag based movement.
        """
        super().__init__(**kwds)
        self.is_slow = is_slow
        self.pixels_to_microns = 1.0
        self.pos_dict = None
        self.stage = stage

    def dragMove(self, x, y):
        """
        Usually used by display.display, units are pixels.
        """
        x = x * self.pixels_to_microns
        y = y * self.pixels_to_microns
        self.maybeRun(task = self.stage.goAbsolute,
                      args = [x, y])

    def getCurrentPosition(self):
        return self.pos_dict

    def goAbsolute(self, x, y):
        """
        Usually used by the stage GUI, units are microns.
        """
        self.mustRun(task = self.stage.goAbsolute,
                     args = [x, y])
    
    def goRelative(self, dx, dy):
        """
        Usually used by the stage GUI, units are microns.
        """
        self.maybeRun(task = self.stage.goRelative,
                      args = [dx, dy])

    def isSlow(self):
        return self.is_slow
        
    def jog(self, xs, ys):
        """
        Usually used by the joystick, units are pixels.
        """
        xs = xs * self.pixels_to_microns
        ys = ys * self.pixels_to_microns
        self.maybeRun(task = self.stage.jog,
                      args = [xs, ys])

    def setPixelsToMicrons(self, pixels_to_microns):
        self.pixels_to_microns = pixels_to_microns

    def wait(self):
        self.updateTimer.stop()
        super().wait()

    def zero(self):
        self.mustRun(task = self.stage.zero)


class StageModule(hardwareModule.HardwareModule):
    """
    Provides a stage functionality whose name is just the module name.

    Some stage controllers can also control additional peripherals.
    Functionalities for these will have names like 'module_name.peripheral'.
    """
    def __init__(self, **kwds):
        super().__init__(**kwds)
        self.stage = None
        self.stage_functionality = None

    def cleanUp(self, qt_settings):
        if self.stage is not None:
            self.stage_functionality.wait()
            self.stage.shutDown()

    def getFunctionality(self, message):
        if (message.getData()["name"] == self.module_name) and (self.stage_functionality is not None):
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"functionality" : self.stage_functionality}))

    def pixelSize(self, message):
        if self.stage is not None:
            self.stage_functionality.setPixelsToMicrons(message.getData()["pixel size"])

    def processMessage(self, message):

        if message.isType("get functionality"):
            self.getFunctionality(message)

        elif message.isType("pixel size"):
            self.pixelSize(message)
            
        elif message.isType("start film"):
            self.startFilm(message)

        elif message.isType("stop film"):
            self.stopFilm(message)
            
    def startFilm(self, message):
        if self.stage is not None:
            self.stage_functionality.mustRun(task = self.stage.joystickOnOff,
                                             args = [False])

    def stopFilm(self, message):
        if self.stage is not None:
            self.stage_functionality.mustRun(task = self.stage.joystickOnOff,
                                             args = [True])
            pos_dict = self.stage_functionality.getCurrentPosition()
            pos_string = "{0:.2f},{1:.2f}".format(pos_dict["x"], pos_dict["y"])
            pos_param = params.ParameterCustom(name = "stage_position",
                                               value = pos_string)
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"acquisition" : [pos_param]}))
