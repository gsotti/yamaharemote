import pycurl
import cStringIO
import xml.etree.ElementTree as ET
import sys

from gi.repository import GObject, Gtk

AMP_ADDRESS = "192.168.1.158"

class YamahaRemoteControl(GObject.GObject):
    __gproperties__ = {
        "volume": (float, "volume",
                   "Output volume",
                   -60.0, 0.0, -40.0,
                   GObject.PARAM_READWRITE),
        "muted": (bool, "muted",
                  "Is audio muted",
                  False,
                  GObject.PARAM_READWRITE),
        "power": (bool, "power",
                  "Is system powered up",
                  True,
                  GObject.PARAM_READWRITE),
        }

    def __init__(self):
        GObject.GObject.__init__(self)

        self.is_power_on = True
        self.volume = 0.0
        self.new_volume = 0.0
        self.is_muted = False

        self.curl = pycurl.Curl()
        self.curl.setopt(pycurl.POST, 1)
        url = "http://%s/YamahaRemoteControl/ctrl" % AMP_ADDRESS
        self.curl.setopt(pycurl.URL, url)
        self.curl.setopt(pycurl.HTTPHEADER,
                ['Content-Type: text/xml; charset="utf-8"', 'Expect:'])

    def __del__(self):
        self.curl.close()

    def do_get_property(self, prop):
        if prop.name == 'volume':
            return self.volume
        elif prop.name == 'muted':
            return self.is_muted
        elif prop.name == 'power':
            return self.is_power_on
        else:
            raise AttributeError, "Unknown property %s" % prop.name

    def do_set_property(self, prop, value):
        if prop.name == 'volume':
            self.set_volume(value)
        elif prop.name == 'muted':
            self.set_is_muted(value)
        elif prop.name == 'power':
            self.set_is_power_on(value)
        else:
            raise AttributeError, "Unknown property %s" % prop.name

    def _exec(self, cmd="GET", data=None):
        req = """<?xml version="1.0" encoding="utf-8"?><YAMAHA_AV cmd="%s">%s</YAMAHA_AV>""" % (cmd, data)
        self.curl.setopt(pycurl.POSTFIELDSIZE, len(req))
        self.curl.setopt(pycurl.READFUNCTION, cStringIO.StringIO(req).read)
        b = cStringIO.StringIO()
        self.curl.setopt(pycurl.WRITEFUNCTION, b.write)
        self.curl.perform()
        return ET.fromstring(b.getvalue())

    def _get(self, data):
        return self._exec("GET", data)

    def _put(self, data):
        return self._exec("PUT", data)

    def set_is_power_on(self, is_power_on):
        if is_power_on != self.is_power_on:
            cmd = "<Main_Zone><Power_Control><Power>%s</Power></Power_Control></Main_Zone>" % ["Standby", "On"][is_power_on]
            self._put(cmd)
            self.is_power_on = is_power_on
            self.notify('power')

    def get_is_power_on(self):
        return self.is_power_on

    def set_volume(self, volume):
        volume = round(volume * 2.0) / 2.0
        if volume != self.volume:
            self.new_volume = volume
            GObject.idle_add(self._set_volume)

    def _set_volume(self):
        if self.volume == self.new_volume:
            return False
        volume = self.new_volume
        req = """<Main_Zone><Volume><Lvl><Val>%d</Val><Exp>1</Exp><Unit>dB</Unit></Lvl></Volume></Main_Zone>""" % round(volume * 10)
        self._put(req)
        if volume != self.volume:
            self.volume = volume
            self.notify('volume')
        return False

    def get_volume(self):
        return self.volume

    def set_is_muted(self, is_muted):
        if is_muted != self.is_muted:
            req = """<Main_Zone><Volume><Mute>%s</Mute></Volume></Main_Zone>""" % ["Off", "On"][is_muted]
            self._put(req)
            self.is_muted = is_muted
            self.notify('muted')

    def get_is_muted(self):
        return self.is_muted

    def refresh(self):
        req = """<Main_Zone><Basic_Status>GetParam</Basic_Status></Main_Zone>"""
        status = self._get(req)[0].find('Basic_Status')

        val = int(status.find("Volume/Lvl/Val").text)
        exp = int(status.find("Volume/Lvl/Exp").text)
        volume = val / 10.0**exp
        if volume != self.volume:
            self.volume = volume
            self.notify('volume')

        is_muted = status.find("Volume/Mute").text == "On"
        if is_muted != self.is_muted:
            self.is_muted = is_muted
            self.notify('muted')

        is_power_on = status.find("Power_Control/Power").text == "On"
        if is_power_on != self.is_power_on:
            self.is_power_on = is_power_on
            self.notify('power')

class YamahaRemoteWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="Yamaha Remote Control")
        self.set_resizable(False)
        self.set_border_width(12)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.add(vbox)

        system_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        vbox.pack_start(system_box, False, False, 6)

        image = Gtk.Image.new_from_icon_name("audio-speakers", Gtk.IconSize.DIALOG)
        system_box.pack_start(image, False, False, 0)

        label = Gtk.Label()
        label.set_markup("<b>RX-V573</b>")
        system_box.pack_start(label, False, False, 0)

        power_box = Gtk.Alignment(xalign=1.0, yalign=0.5, xscale=0.0, yscale=0.0)
        self.power_switch = Gtk.Switch()
        self.power_switch.set_active(True)
        self.power_switch.connect('notify::active', self.on_power_notify)
        power_box.add(self.power_switch)
        system_box.pack_start(power_box, True, True, 0)

        volume_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        alignment = Gtk.Alignment(xalign=0, yalign=0, xscale=1, yscale=1)
        alignment.set_padding(12, 0, 0, 0)
        alignment.add(volume_box)
        vbox.pack_start(alignment, False, False, 6)

        label = Gtk.Label()
        label.set_label("Volume:")
        label.set_alignment(0.0, 0.5)
        label.get_style_context().add_class('dim-label')
        volume_box.pack_start(label, False, False, 0)

        adj = Gtk.Adjustment(-40.0, -80.0, 16.0, 0.5, 5.0, 0.0)
        self.volume_bar = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                adjustment=adj)
        self.volume_bar.set_size_request(128, -1)
        self.volume_bar.set_draw_value(False)
        self.volume_bar.add_mark(0.0, Gtk.PositionType.BOTTOM,
                "<small>100%</small>")
        adj.connect('value-changed', self.on_volume_changed)
        volume_box.pack_start(self.volume_bar, True, True, 0)

        mute_box = Gtk.Alignment(xalign=0.5, yalign=0.0, xscale=0.0, yscale=0.0)
        self.mute_switch = Gtk.Switch()
        self.mute_switch.set_active(True)
        self.mute_switch.connect('notify::active', self.on_is_muted_notify)
        mute_box.add(self.mute_switch)
        volume_box.pack_start(mute_box, False, False, 0)

        self.remote = YamahaRemoteControl()
        self.remote.connect("notify::volume", self.on_remote_volume_notify)
        self.remote.connect("notify::muted", self.on_remote_muted_notify)
        self.remote.connect("notify::power", self.on_remote_power_notify)
        self.remote.refresh()

    def on_power_notify(self, switch, data):
        self.remote.set_is_power_on(switch.get_active())

    def on_remote_power_notify(self, remote, data):
        self.power_switch.freeze_notify()
        self.power_switch.set_active(self.remote.get_is_power_on())
        self.power_switch.thaw_notify()

    def on_volume_changed(self, adjustment):
        volume = adjustment.get_value()
        self.remote.set_volume(volume)

    def on_remote_volume_notify(self, remote, data):
        adj = self.volume_bar.get_adjustment()
        adj.handler_block_by_func(self.on_volume_changed)
        adj.set_value(self.remote.get_volume())
        adj.handler_unblock_by_func(self.on_volume_changed)

    def on_is_muted_notify(self, switch, active):
        self.remote.set_is_muted(not switch.get_active())

    def on_remote_muted_notify(self, remote, data):
        self.mute_switch.freeze_notify()
        self.mute_switch.set_active(not self.remote.get_is_muted())
        self.mute_switch.thaw_notify()

if __name__ == '__main__':
    win = YamahaRemoteWindow()
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()
    Gtk.main()
