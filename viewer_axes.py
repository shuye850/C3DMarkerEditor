"""Use the whole rectangular viewport without stretching 3D geometry."""
from mpl_toolkits.mplot3d import Axes3D
from matplotlib.projections import register_projection

class WorkspaceAxes3D(Axes3D):
    name='workspace3d'
    def apply_aspect(self,position=None):
        if position is None:position=self.get_position(original=True)
        self._set_position(position,which='active')
    def get_proj(self):
        matrix=super().get_proj()
        box=self.get_window_extent()
        if box.width>0:matrix[0,:]*=box.height/box.width
        return matrix

register_projection(WorkspaceAxes3D)
