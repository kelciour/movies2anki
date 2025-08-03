local mp = require 'mp'

local function save_settings()
	mp.command("write-watch-later-config")
end

mp.observe_property("vf", "string", save_settings)

local function close_window()
	mp.command('quit')
end

mp.add_key_binding("й", "close_window", close_window)
