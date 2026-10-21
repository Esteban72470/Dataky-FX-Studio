-- Minimal Roblox API stand-ins used by tool/test_fx_rbxmx.py to execute the exported
-- .rbxmx player outside Studio. Only what fx_runtime.lua touches is modelled; every
-- property write is recorded so the test can check the timeline.
NOW = 0
EVENTS = {}
local function record(...)
    table.insert(EVENTS, table.concat({...}, " "))
end

local function class(name, fields)
    local mt = {__type = name}
    mt.__index = function(self, key)
        local getter = fields.getters and fields.getters[key]
        if getter then return getter(self) end
        return fields[key]
    end
    return mt
end

local Vector3Mt
Vector3Mt = class("Vector3", {
    getters = {Magnitude = function(v) return math.sqrt(v.X * v.X + v.Y * v.Y + v.Z * v.Z) end},
    Lerp = function(a, b, t) return Vector3.new(a.X + (b.X - a.X) * t, a.Y + (b.Y - a.Y) * t, a.Z + (b.Z - a.Z) * t) end,
})
Vector3 = {new = function(x, y, z) return setmetatable({X = x or 0, Y = y or 0, Z = z or 0}, Vector3Mt) end}
Vector3Mt.__add = function(a, b) return Vector3.new(a.X + b.X, a.Y + b.Y, a.Z + b.Z) end
Vector3Mt.__sub = function(a, b) return Vector3.new(a.X - b.X, a.Y - b.Y, a.Z - b.Z) end
Vector3Mt.__mul = function(a, b)
    if type(a) == "number" then a, b = b, a end
    return Vector3.new(a.X * b, a.Y * b, a.Z * b)
end
Vector3.zero = Vector3.new(0, 0, 0)

local Vector2Mt = class("Vector2", {Lerp = function(a, b, t) return Vector2.new(a.X + (b.X - a.X) * t, a.Y + (b.Y - a.Y) * t) end})
Vector2 = {new = function(x, y) return setmetatable({X = x or 0, Y = y or 0}, Vector2Mt) end}
local Color3Mt = class("Color3", {Lerp = function(a, b, t) return Color3.new(a.R + (b.R - a.R) * t, a.G + (b.G - a.G) * t, a.B + (b.B - a.B) * t) end})
Color3 = {new = function(r, g, b) return setmetatable({R = r, G = g, B = b}, Color3Mt) end}
local RangeMt = class("NumberRange", {})
NumberRange = {new = function(a, b) return setmetatable({Min = a, Max = b or a}, RangeMt) end}
local function sequence(kind)
    local mt = class(kind, {})
    return {new = function(points) return setmetatable({Keypoints = points}, mt) end}
end
NumberSequence, ColorSequence = sequence("NumberSequence"), sequence("ColorSequence")
NumberSequenceKeypoint = {new = function(t, v, e) return {Time = t, Value = v, Envelope = e} end}
ColorSequenceKeypoint = {new = function(t, v) return {Time = t, Value = v} end}
CFrame = {new = function(x, y, z) return {X = x or 0, Y = y or 0, Z = z or 0} end}
Enum = setmetatable({}, {__index = function(_, enumName)
    return setmetatable({}, {__index = function(_, item) return {Name = item, EnumType = enumName} end})
end})
typeof = function(value)
    local mt = getmetatable(value)
    if type(value) == "table" and type(mt) == "table" and mt.__type then return mt.__type end
    return type(value)
end
warn = function(...) record("WARN", ...) end

local InstanceMt = {__type = "Instance"}
local methods = {}
InstanceMt.__index = function(self, key)
    if methods[key] then return methods[key] end
    return rawget(self, "_props")[key]
end
InstanceMt.__newindex = function(self, key, value)
    local id = rawget(self, "_attributes").DatakyFXNodeId or rawget(self, "Name")
    if key == "Enabled" and rawget(self, "_props").Enabled ~= value then
        record("ENABLED", id, string.format("%.3f", NOW), tostring(value))
    elseif key == "Position" and typeof(value) == "Vector3" then
        record("POSITION", id, string.format("%.3f", NOW), string.format("%.3f %.3f %.3f", value.X, value.Y, value.Z))
    end
    rawget(self, "_props")[key] = value
end
function methods.GetAttribute(self, key) return rawget(self, "_attributes")[key] end
function methods.SetAttribute(self, key, value) rawget(self, "_attributes")[key] = value end
function methods.GetChildren(self) return table.clone(rawget(self, "_children")) end
function methods.GetDescendants(self)
    local out = {}
    local function walk(node)
        for _, child in ipairs(rawget(node, "_children")) do table.insert(out, child); walk(child) end
    end
    walk(self)
    return out
end
function methods.GetFullName(self) return rawget(self, "Name") end
function methods.IsA(self, className) return className == "PVInstance" and (self.ClassName == "Model" or self.ClassName == "Part") or self.ClassName == className end
function methods.GetPivot(self) return rawget(self, "_pivot") or CFrame.new(0, 0, 0) end
function methods.Emit(self, count) record("EMIT", rawget(self, "_attributes").DatakyFXNodeId, string.format("%.3f", NOW), tostring(count)) end
function methods.Clear(self) end
function methods.Destroy(self) record("DESTROY", rawget(self, "Name")) end
function methods.FindFirstChild(self, name)
    for _, child in ipairs(rawget(self, "_children")) do if rawget(child, "Name") == name then return child end end
    return nil
end

function MakeInstance(className, name, attributes, parent)
    local object = setmetatable({Name = name, _props = {ClassName = className, Name = name, Enabled = true}, _attributes = attributes or {}, _children = {}}, InstanceMt)
    if parent then table.insert(rawget(parent, "_children"), object); rawget(object, "_props").Parent = parent end
    return object
end

local heartbeat = nil
local Workspace = MakeInstance("Workspace", "Workspace")
local services = {
    Workspace = Workspace,
    RunService = {Heartbeat = {Connect = function(_, fn) heartbeat = fn; return {Disconnect = function() heartbeat = nil end} end}},
    AssetService = {}, ContentProvider = {},
}
game = {GetService = function(_, name) return services[name] end}
workspace = Workspace

function Step(dt)
    NOW += dt
    if heartbeat then heartbeat(dt) end
end
function Dump()
    for _, line in ipairs(EVENTS) do print(line) end
end
