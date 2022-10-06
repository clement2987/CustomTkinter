import tkinter
import tkinter.ttk as ttk
import copy
import re
from typing import Union, Callable

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict

from ..windows.ctk_tk import CTk
from ..windows.ctk_toplevel import CTkToplevel
from ..appearance_mode_tracker import AppearanceModeTracker
from ..scaling_tracker import ScalingTracker
from ..theme_manager import ThemeManager

from .widget_helper_functions import pop_from_dict_by_set


class CTkBaseClass(tkinter.Frame):
    """ Base class of every CTk widget, handles the dimensions, _bg_color,
        appearance_mode changes, scaling, bg changes of master if master is not a CTk widget """

    # attributes that are passed to and managed by the tkinter frame only:
    _valid_tk_frame_attributes = {"cursor"}

    def __init__(self,
                 master: any = None,
                 width: int = 0,
                 height: int = 0,

                 bg_color: Union[str, tuple] = None,
                 **kwargs):

        super().__init__(master=master, width=width, height=height, **pop_from_dict_by_set(kwargs, self._valid_tk_frame_attributes))

        # check if kwargs is empty, if not raise error for unsupported arguments
        self._check_kwargs_empty(kwargs, raise_error=True)

        # dimensions
        self._current_width = width  # _current_width and _current_height in pixel, represent current size of the widget
        self._current_height = height  # _current_width and _current_height are independent of the scale
        self._desired_width = width  # _desired_width and _desired_height, represent desired size set by width and height
        self._desired_height = height

        # scaling
        ScalingTracker.add_widget(self._set_scaling, self)  # add callback for automatic scaling changes
        self._widget_scaling = ScalingTracker.get_widget_scaling(self)
        self._spacing_scaling = ScalingTracker.get_spacing_scaling(self)

        super().configure(width=self._apply_widget_scaling(self._desired_width),
                          height=self._apply_widget_scaling(self._desired_height))

        # save latest geometry function and kwargs
        class GeometryCallDict(TypedDict):
            function: Callable
            kwargs: dict

        self._last_geometry_manager_call: Union[GeometryCallDict, None] = None

        # add set_appearance_mode method to callback list of AppearanceModeTracker for appearance mode changes
        AppearanceModeTracker.add(self._set_appearance_mode, self)
        self._appearance_mode = AppearanceModeTracker.get_mode()  # 0: "Light" 1: "Dark"

        # background color
        self._bg_color = self._detect_color_of_master() if bg_color is None else bg_color

        super().configure(bg=ThemeManager.single_color(self._bg_color, self._appearance_mode))

        # overwrite configure methods of master when master is tkinter widget, so that bg changes get applied on child CTk widget as well
        if isinstance(self.master, (tkinter.Tk, tkinter.Toplevel, tkinter.Frame)) and not isinstance(self.master, (CTkBaseClass, CTk, CTkToplevel)):
            master_old_configure = self.master.config

            def new_configure(*args, **kwargs):
                if "bg" in kwargs:
                    self.configure(bg_color=kwargs["bg"])
                elif "background" in kwargs:
                    self.configure(bg_color=kwargs["background"])

                # args[0] is dict when attribute gets changed by widget[<attribute>] syntax
                elif len(args) > 0 and type(args[0]) == dict:
                    if "bg" in args[0]:
                        self.configure(bg_color=args[0]["bg"])
                    elif "background" in args[0]:
                        self.configure(bg_color=args[0]["background"])
                master_old_configure(*args, **kwargs)

            self.master.config = new_configure
            self.master.configure = new_configure

    @staticmethod
    def _check_kwargs_empty(kwargs_dict, raise_error=False) -> bool:
        """ returns True if kwargs are empty, False otherwise, raises error if not empty """

        if len(kwargs_dict) > 0:
            if raise_error:
                raise ValueError(f"{list(kwargs_dict.keys())} are not supported arguments. Look at the documentation for supported arguments.")
            else:
                return True
        else:
            return False

    def destroy(self):
        AppearanceModeTracker.remove(self._set_appearance_mode)
        super().destroy()

    def place(self, **kwargs):
        self._last_geometry_manager_call = {"function": super().place, "kwargs": kwargs}
        return super().place(**self._apply_argument_scaling(kwargs))

    def place_forget(self):
        self._last_geometry_manager_call = None
        return super().place_forget()

    def pack(self, **kwargs):
        self._last_geometry_manager_call = {"function": super().pack, "kwargs": kwargs}
        return super().pack(**self._apply_argument_scaling(kwargs))

    def pack_forget(self):
        self._last_geometry_manager_call = None
        return super().pack_forget()

    def grid(self, **kwargs):
        self._last_geometry_manager_call = {"function": super().grid, "kwargs": kwargs}
        return super().grid(**self._apply_argument_scaling(kwargs))

    def grid_forget(self):
        self._last_geometry_manager_call = None
        return super().grid_forget()

    def _apply_argument_scaling(self, kwargs: dict) -> dict:
        scaled_kwargs = copy.copy(kwargs)

        if "pady" in scaled_kwargs:
            if isinstance(scaled_kwargs["pady"], (int, float, str)):
                scaled_kwargs["pady"] = self._apply_spacing_scaling(scaled_kwargs["pady"])
            elif isinstance(scaled_kwargs["pady"], tuple):
                scaled_kwargs["pady"] = tuple([self._apply_spacing_scaling(v) for v in scaled_kwargs["pady"]])
        if "padx" in kwargs:
            if isinstance(scaled_kwargs["padx"], (int, float, str)):
                scaled_kwargs["padx"] = self._apply_spacing_scaling(scaled_kwargs["padx"])
            elif isinstance(scaled_kwargs["padx"], tuple):
                scaled_kwargs["padx"] = tuple([self._apply_spacing_scaling(v) for v in scaled_kwargs["padx"]])

        if "x" in scaled_kwargs:
            scaled_kwargs["x"] = self._apply_spacing_scaling(scaled_kwargs["x"])
        if "y" in scaled_kwargs:
            scaled_kwargs["y"] = self._apply_spacing_scaling(scaled_kwargs["y"])

        return scaled_kwargs

    def _draw(self, no_color_updates: bool = False):
        """ abstract of draw method to be overridden """
        pass

    def config(self, *args, **kwargs):
        raise AttributeError("'config' is not implemented for CTk widgets. For consistency, always use 'configure' instead.")

    def configure(self, require_redraw=False, **kwargs):
        """ basic configure with bg_color support, calls configure of tkinter.Frame, calls draw() in the end """

        if "bg_color" in kwargs:
            new_bg_color = kwargs.pop("bg_color")
            if new_bg_color is None:
                self._bg_color = self._detect_color_of_master()
            else:
                self._bg_color = new_bg_color
            require_redraw = True

        super().configure(**pop_from_dict_by_set(kwargs, self._valid_tk_frame_attributes))  # configure tkinter.Frame

        # if there are still items in the kwargs dict, raise ValueError
        self._check_kwargs_empty(kwargs, raise_error=True)

        if require_redraw:
            self._draw()

    def cget(self, attribute_name: str):
        """ basic cget with bg_color, width, height support, calls cget of tkinter.Frame """

        if attribute_name == "bg_color":
            return self._bg_color
        elif attribute_name == "width":
            return self._desired_width
        elif attribute_name == "height":
            return self._desired_height

        elif attribute_name in self._valid_tk_frame_attributes:
            return super().cget(attribute_name)  # cget of tkinter.Frame
        else:
            raise ValueError(f"'{attribute_name}' is not a supported argument. Look at the documentation for supported arguments.")

    def _update_dimensions_event(self, event):
        # only redraw if dimensions changed (for performance), independent of scaling
        if round(self._current_width) != round(event.width / self._widget_scaling) or round(self._current_height) != round(event.height / self._widget_scaling):
            self._current_width = (event.width / self._widget_scaling)  # adjust current size according to new size given by event
            self._current_height = (event.height / self._widget_scaling)  # _current_width and _current_height are independent of the scale

            self._draw(no_color_updates=True)  # faster drawing without color changes

    def _detect_color_of_master(self, master_widget=None):
        """ detect color of self.master widget to set correct _bg_color """

        if master_widget is None:
            master_widget = self.master

        if isinstance(master_widget, (CTkBaseClass, CTk, CTkToplevel)) and hasattr(master_widget, "_fg_color"):
            if master_widget._fg_color is not None:
                return master_widget._fg_color

            # if fg_color of master is None, try to retrieve fg_color from master of master
            elif hasattr(master_widget.master, "master"):
                return self._detect_color_of_master(master_widget.master)

        elif isinstance(master_widget, (ttk.Frame, ttk.LabelFrame, ttk.Notebook, ttk.Label)):  # master is ttk widget
            try:
                ttk_style = ttk.Style()
                return ttk_style.lookup(master_widget.winfo_class(), 'background')
            except Exception:
                return "#FFFFFF", "#000000"

        else:  # master is normal tkinter widget
            try:
                return master_widget.cget("bg")  # try to get bg color by .cget() method
            except Exception:
                return "#FFFFFF", "#000000"

    def _set_appearance_mode(self, mode_string):
        if mode_string.lower() == "dark":
            self._appearance_mode = 1
        elif mode_string.lower() == "light":
            self._appearance_mode = 0

        super().configure(bg=ThemeManager.single_color(self._bg_color, self._appearance_mode))
        self._draw()

    def _set_scaling(self, new_widget_scaling, new_spacing_scaling, new_window_scaling):
        self._widget_scaling = new_widget_scaling
        self._spacing_scaling = new_spacing_scaling

        super().configure(width=self._apply_widget_scaling(self._desired_width),
                          height=self._apply_widget_scaling(self._desired_height))

        if self._last_geometry_manager_call is not None:
            self._last_geometry_manager_call["function"](**self._apply_argument_scaling(self._last_geometry_manager_call["kwargs"]))

    def _set_dimensions(self, width=None, height=None):
        if width is not None:
            self._desired_width = width
        if height is not None:
            self._desired_height = height

        super().configure(width=self._apply_widget_scaling(self._desired_width),
                          height=self._apply_widget_scaling(self._desired_height))

    def _apply_widget_scaling(self, value: Union[int, float, str]) -> Union[float, str]:
        if isinstance(value, (int, float)):
            return value * self._widget_scaling
        else:
            return value

    def _apply_spacing_scaling(self, value: Union[int, float, str]) -> Union[float, str]:
        if isinstance(value, (int, float)):
            return value * self._spacing_scaling
        else:
            return value

    def _apply_font_scaling(self, font):
        if type(font) == tuple or type(font) == list:
            font_list = list(font)
            for i in range(len(font_list)):
                if (type(font_list[i]) == int or type(font_list[i]) == float) and font_list[i] < 0:
                    font_list[i] = int(font_list[i] * self._widget_scaling)
            return tuple(font_list)

        elif type(font) == str:
            for negative_number in re.findall(r" -\d* ", font):
                font = font.replace(negative_number, f" {int(int(negative_number) * self._widget_scaling)} ")
            return font

        elif isinstance(font, tkinter.font.Font):
            new_font_object = copy.copy(font)
            if font.cget("size") < 0:
                new_font_object.config(size=int(font.cget("size") * self._widget_scaling))
            return new_font_object

        else:
            return font
