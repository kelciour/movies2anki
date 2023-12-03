local mp = require 'mp'

local function save_settings()
	mp.command("write-watch-later-config")
end

mp.observe_property("vf", "string", save_settings)