-- https://github.com/mpv-player/mpv/issues/7204#issuecomment-835537051

local msg = require 'mp.msg'

function on_width_change(name, osd_w)
	if osd_w ~= nil then
		osd_h = mp.get_property_number("osd-dimensions/h")
		local geometry = ("%dx%d"):format(osd_w, osd_h)
		msg.debug("OSD resized: " .. geometry .. ", setting geometry property")
		mp.set_property_native("geometry", geometry)
	end
end
mp.observe_property("osd-dimensions/w", "number", on_width_change)