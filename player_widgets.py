from PySide6 import QtWidgets as W,QtCore,QtGui

class Timeline(W.QSlider):
    """Full-trial transport scrubber with a time ruler."""
    selectionCleared=QtCore.Signal()
    def __init__(self,parent=None):
        super().__init__(QtCore.Qt.Orientation.Horizontal,parent)
        self.first_frame=0;self.rate=1.;self.setMinimumHeight(48)
    def mouseDoubleClickEvent(self,event):
        if event.button()==QtCore.Qt.MouseButton.LeftButton:
            self.selectionCleared.emit();event.accept();return
        super().mouseDoubleClickEvent(event)
    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QtGui.QPainter(self);painter.setPen(QtGui.QColor('#8291a8'))
        font=painter.font();font.setPixelSize(10);painter.setFont(font)
        count=max(2,self.width()//100)
        for i in range(count+1):
            fraction=i/count;x=8+fraction*(self.width()-16)
            seconds=fraction*(self.maximum()-self.minimum())/self.rate
            text=f'{int(seconds)//60:02d}:{seconds%60:04.1f}'
            painter.drawLine(QtCore.QPointF(x,31),QtCore.QPointF(x,34))
            painter.drawText(QtCore.QRectF(max(0,min(self.width()-50,x-25)),35,50,12),QtCore.Qt.AlignmentFlag.AlignCenter,text)
