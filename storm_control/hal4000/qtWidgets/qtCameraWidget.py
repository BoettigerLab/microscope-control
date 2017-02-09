#!/usr/bin/env python
"""
Qt Widget for handling the display of camera data.

Hazen 02/17
"""

from PyQt5 import QtCore, QtGui, QtWidgets

import numpy
import sys

import storm_control.hal4000.halLib.c_image_manipulation_c as c_image


class QCameraWidget(QtWidgets.QWidget):
    """
    Class for displaying images from the camera.
    """
    displayCaptured = QtCore.pyqtSignal(object)
    dragStart = QtCore.pyqtSignal()
    dragMove = QtCore.pyqtSignal(int, int)
    intensityInfo = QtCore.pyqtSignal(int, int, int)
    mousePress = QtCore.pyqtSignal(int, int)
    roiSelection = QtCore.pyqtSignal(object)

    def __init__(self, **kwds):
        super().__init__(**kwds)

        self.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.setMouseTracking(True)

        self.buffer = False

        # These are for dragging (to move the stage).
        self.ctrl_key_down = False
        self.drag_enabled = False
        self.drag_mode = False
        self.drag_multiplier = None
        self.drag_x = 0
        self.drag_y = 0

        # Boolean to control pixel display.
        self.display_saturated_pixels = False 

        self.flip_horizontal = False
        self.flip_vertical = False
        self.transpose = False

        self.image = False
        self.image_min = 0
        self.image_max = 1

        # This is the amount of image magnification.
        # Only integer values are allowed.
        self.magnification = 1

        self.max_intensity = None
        
        self.mouse_x = 0
        self.mouse_y = 0

        self.roi_rubber_band = False

        self.show_grid = False
        self.show_info = True
        self.show_target = False
 
        # This is the x location of the last mouse click.
        self.x_click = 0

        # This is the x size of the image buffer.
        self.x_final = 10

        # This is the x size of the current camera AOI
        # (divided by binning) in pixels.
        self.x_size = 0

        # This the (minimum) x size of the widget. The image from 
        # the camera cannot be rendered smaller than this value.
        self.x_view = 512

        # These are the same as for x.
        self.y_click = 0
        self.y_final = 10
        self.y_size = 0
        self.y_view = 512

    def blank(self):
        """
        Initialize the off-screen buffer for image rendering.
        """
        painter = QtGui.QPainter(self.buffer)
        color = QtGui.QColor(0, 0, 0)
        painter.setPen(color)
        painter.setBrush(color)
        painter.drawRect(0, 0, self.width(), self.height())

    def calcFinalSize(self):
        """  
        'Final' is the size at which to draw the pixmap that will actually 
        be shown in the window.
        
        Based on the final size, determine the best size for a square window. 
        Set the widget size to this & create a buffer of this size. We'll
        draw in the buffer first, then copy to the window.
        """
        self.x_final = self.x_view
        self.y_final = self.y_view
        if (self.x_size > self.y_size):
            self.y_final = self.x_view * self.y_size / self.x_size
        elif (self.x_size < self.y_size):
            self.x_final = self.y_view * self.x_size / self.y_size

        self.x_final = self.x_final * self.magnification
        self.y_final = self.y_final * self.magnification

        w_size = self.x_final
        if (self.y_final > self.x_final):
            w_size = self.y_final

        self.setFixedSize(w_size, w_size)
        self.buffer = QtGui.QPixmap(w_size, w_size)

        self.blank()

    def getAutoScale(self):
        """
        Returns the minimum and maximum values to use for automatically
        re-scaling the image based on the most recent camera data.
        """
        margin = int(0.1 * float(self.image_max - self.image_min))
        return [self.image_min - margin, self.image_max + margin]

    def getEventLocation(self, event):
        """
        Returns the location of an external event in the window, normalized
        to 0.0 - 1.0.
        """
        event_pos = self.mapFromGlobal(event.globalPos())
        return [float(event_pos.x())/float(self.x_final),
                float(event_pos.y())/float(self.y_final)]

    def keyPressEvent(self, event):
        if (event.key() == QtCore.Qt.Key_Control):
            self.ctrl_key_down = True
            QtGui.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.OpenHandCursor))

    def keyReleaseEvent(self, event):
        if (event.key() == QtCore.Qt.Key_Control):
            self.ctrl_key_down = False
            if not self.drag_mode:
                QtGui.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.ArrowCursor))
        
    def mouseMoveEvent(self, event):
        self.mouse_x = event.x()
        self.mouse_y = event.y()

        if self.roi_rubber_band:
            self.roi_rubber_band.setGeometry(QtCore.QRect(self.roi_rubber_band.pos(), event.pos()).normalized())

        #
        # FIXME: Need to also adjust for binning, current magnification..
        #
        if self.drag_mode:
            dx = self.drag_multiplier * (self.mouse_x - self.drag_x)
            dy = self.drag_multiplier * (self.mouse_y - self.drag_y)
            self.dragMove.emit(dx, dy)

    def mousePressEvent(self, event):
        """
        Convert the mouse click location into camera pixels. The xy 
        coordinates of the event are correctly adjusted for the scroll 
        bar position, we just need to scale them correctly. This causes
        a mousePress event to be emitted.
        """
        # Point/pixel selection.
        self.x_click = int(event.x() * self.x_size / self.x_final)
        self.y_click = int(event.y() * self.y_size / self.y_final)
        
        if (self.x_click >= self.x_size):
            self.x_click = self.x_size - 1
        if (self.y_click >= self.y_size):
            self.y_click = self.y_size - 1
        
        self.mousePress.emit(self.x_click, self.y_click)

        if self.ctrl_key_down and self.drag_enabled:
            self.drag_mode = True
            self.dragStart.emit()
            self.drag_x = event.x()
            self.drag_y = event.y()
            QtGui.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.ClosedHandCursor))

        # ROI selection rubber band.
        else:
            if not self.roi_rubber_band:
                self.roi_rubber_band = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)
            self.roi_rubber_band.setGeometry(QtCore.QRect(event.pos(), QtCore.QSize()))
            self.roi_rubber_band.show()

    def mouseReleaseEvent(self, event):

        if self.drag_mode:
            self.drag_mode = False
            if self.ctrl_key_down:
                QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.OpenHandCursor))
            else:
                QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.ArrowCursor))

        else:
            self.roi_rubber_band.hide()
            rect = self.roi_rubber_band.geometry()
            if (rect.width() > 1) and (rect.height() > 1):
                left = rect.left() * self.x_size / self.x_final
                top = rect.top() * self.y_size / self.y_final
                width = rect.width() * self.x_size / self.x_final
                height = rect.height() * self.y_size / self.y_final
                self.roiSelection.emit(QtCore.QRect(left, top, width, height))
        
    def newColorTable(self, colortable):
        """
        Note that the color table of the image that is being displayed 
        will not actually change until updateImageWithFrame() is called.
        """
        self.colortable = colortable

    def newParameters(self, parameters):
        self.flip_horizontal = parameters.get("flip_horizontal")
        self.flip_vertical = parameters.get("flip_vertical")
        self.transpose = parameters.get("transpose")
        self.drag_multiplier = parameters.get("drag_multiplier", 1.0)
        self.max_intensity = parameters.get("max_intensity")

        if "_sat.ctbl" in parameters.get("colortable"):
            self.display_saturated_pixels = True
        else:
            self.display_saturated_pixels = False
            
    def newRange(self, new_range):
        self.display_range = new_range

    def newSize(self, new_size):
        self.x_size = new_size[0]
        self.y_size = new_size[1]
        self.calcFinalSize()

    def paintEvent(self, event):
        """
        self.image is the image from the camera scaled to the buffer size.
        
        self.buffer is where the image is temporarily re-drawn prior 
        to final display. In theory this reduces display flickering.
        """
        if self.image:
            painter = QtGui.QPainter(self.buffer)

            # Draw current image into the buffer, appropriately scaled.
            # Only draw what is actually visible.
            vr = self.visibleRegion().boundingRect()
            painter.drawImage(vr, self.image, vr)

            # Draw the grid into the buffer.
            if self.show_grid:
                x_step = self.width()/8
                y_step = self.height()/8
                painter.setPen(QtGui.QColor(255, 255, 255))
                for i in range(7):
                    painter.drawLine((i+1)*x_step, 0, (i+1)*x_step, self.height())
                    painter.drawLine(0, (i+1)*y_step, self.width(), (i+1)*y_step)

            # Draw the target into the buffer
            if self.show_target:
                mid_x = self.width()/2 - 20
                mid_y = self.height()/2 - 20
                painter.setPen(QtGui.QColor(255, 255, 255))
                painter.drawEllipse(mid_x, mid_y, 40, 40)

            # Transfer the buffer to the screen.
            painter = QtGui.QPainter(self)
            painter.drawPixmap(0, 0, self.buffer)

            # Draw a version for any external devices that want a copy
            # of whatever is currently displayed by this widget.
            a_pixmap = QtGui.QPixmap(vr.width(), vr.height())
            painter = QtGui.QPainter(a_pixmap)
            painter.drawImage(a_pixmap.rect(), self.image, vr)
            self.displayCaptured.emit(a_pixmap)

    def setColorTable(self):
        """
        Changes the color table of the current image.
        """
        if self.colortable:
            for i in range(256):
                self.image.setColor(i, QtGui.qRgb(self.colortable[i][0], 
                                                  self.colortable[i][1], 
                                                  self.colortable[i][2]))
        else:
            for i in range(256):
                self.image.setColor(i,QtGui.qRgb(i,i,i))

    def setDragEnabled(self, drag_enabled):
        """
        Allow mouse drags and emit when the ctrl key is pressed and the
        mouse is dragged across the screen.
        """
        self.drag_enabled = drag_enabled
                       
    def setMagnification(self, new_magnification):
        """
        Note that the magnification of the image that is being displayed 
        will not actually change until updateImageWithFrame() is called.
        """
        self.magnification = new_magnification
        self.calcFinalSize()

    def setShowGrid(self, show_grid):
        """
        Overlay a grid on the image from the camera.
        """
        self.show_grid = show_grid

    def setShowInfo(self, show_info):
        """
        Display intensity information for the last pixel that was clicked on.
        """
        self.show_info = show_info

    def setShowTarget(self, show_target):
        """
        Overlay a circle in the center of the image from the camera.
        """
        self.show_targe = show_target

    def updateImageWithFrame(self, frame):
        """
        This takes the image from the camera, scales it, resizes it and converts it
        into a QImage that can be drawn in the display. It also emits the intensityInfo
        signal with the current intensity of the pixel of interest.
        """
        w = frame.image_x
        h = frame.image_y
        image_data = frame.getData()
        try:
            image_data = image_data.reshape((h,w))
        except ValueError as e:
            print("Got an image with an unexpected size, ", image_data.size, "expected", h * w)
            return

        max_intensity = self.max_intensity
        if not self.display_saturated_pixels:
            max_intensity = None
                
        [temp, self.image_min, self.image_max] = c_image.rescaleImage(image_data,
                                                                      self.flip_horizontal,
                                                                      self.flip_vertical,
                                                                      self.transpose,
                                                                      self.display_range,
                                                                      max_intensity)

        # Create QImage & draw at final magnification.
        if self.transpose:
            temp_image = QtGui.QImage(temp.data, h, w, QtGui.QImage.Format_Indexed8)
            self.image = temp_image.scaled(self.y_final, self.x_final)
        else:
            temp_image = QtGui.QImage(temp.data, w, h, QtGui.QImage.Format_Indexed8)
            self.image = temp_image.scaled(self.x_final, self.y_final)
        self.image.ndarray = temp

        # Set the images color table.
        self.setColorTable()
        self.update()

        if self.show_info:
            x_loc = self.x_click
            y_loc = self.y_click
            value = 0
            if ((x_loc >= 0) and (x_loc < w) and (y_loc >= 0) and (y_loc < h)):
                value = image_data[y_loc, x_loc]
                self.intensityInfo.emit(x_loc, y_loc, value)


#
# Testing
#

#if (__name__ == "__main__"):
#    class Parameters:
#        def __init__(self):
#            self.x_pixels = 200
#            self.y_pixels = 200
#
#    parameters = Parameters()
#    app = QtWidgets.QApplication(sys.argv)
#    viewer = QCameraWidget(parameters, [200,400])
#    viewer.show()
#
#    sys.exit(app.exec_())


#
# The MIT License
#
# Copyright (c) 2017 Zhuang Lab, Harvard University
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
