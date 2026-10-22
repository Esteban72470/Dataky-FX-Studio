-- Minimal Roblox API stand-ins used by tool/test_fx_rbxmx.py to execute the exported
-- .rbxmx player outside Studio. Only what fx_runtime.lua touches is modelled; every
-- property write is recorded so the test can check the timeline.
NOW = 0
EVENTS = {}
MOCK_STATS = {newCalls=0, cloneCalls=0, propertyWrites=0}
local recording = true
function SetMockRecording(value) recording = value end
local function record(...)
    if recording then table.insert(EVENTS, table.concat({...}, " ")) end
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
Vector2Mt.__mul = function(a, b)
    if type(a) == "number" then a, b = b, a end
    return Vector2.new(a.X * b, a.Y * b)
end
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
local CFrameMt
CFrameMt = class("CFrame", {
    getters = {Position = function(cf) return Vector3.new(cf.X, cf.Y, cf.Z) end},
    VectorToWorldSpace = function(cf, v)
        local r = cf.R
        return Vector3.new(r[1]*v.X+r[2]*v.Y+r[3]*v.Z, r[4]*v.X+r[5]*v.Y+r[6]*v.Z, r[7]*v.X+r[8]*v.Y+r[9]*v.Z)
    end,
})
CFrame = {new = function(x, y, z)
    if type(x) == "table" then x, y, z = x.X, x.Y, x.Z end
    return setmetatable({X=x or 0, Y=y or 0, Z=z or 0, R={1,0,0,0,1,0,0,0,1}}, CFrameMt)
end}
CFrameMt.__mul = function(a, b)
    if getmetatable(b) == Vector3Mt then return a.Position + a:VectorToWorldSpace(b) end
    local out, ar, br = CFrame.new(a.Position + a:VectorToWorldSpace(b.Position)), a.R, b.R
    for row = 0, 2 do
        for col = 0, 2 do
            out.R[row*3+col+1] = ar[row*3+1]*br[col+1] + ar[row*3+2]*br[col+4] + ar[row*3+3]*br[col+7]
        end
    end
    return out
end
CFrame.fromOrientation = function(x, y, z)
    local cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    local rx, ry, rz = CFrame.new(), CFrame.new(), CFrame.new()
    rx.R, ry.R, rz.R = {1,0,0,0,cx,-sx,0,sx,cx}, {cy,0,sy,0,1,0,-sy,0,cy}, {cz,-sz,0,sz,cz,0,0,0,1}
    return ry * rx * rz -- Roblox Orientation is YXZ.
end
CFrame.Angles = function(x, y, z)
    local rx, ry, rz = CFrame.fromOrientation(x,0,0), CFrame.fromOrientation(0,y,0), CFrame.fromOrientation(0,0,z)
    return rx * ry * rz
end
Enum = setmetatable({}, {__index = function(enums, enumName)
    local enum = setmetatable({}, {__index = function(items, item)
        local value = setmetatable({Name=item, EnumType=enumName}, {__tostring=function() return "Enum." .. enumName .. "." .. item end})
        rawset(items, item, value)
        return value
    end})
    rawset(enums, enumName, enum)
    return enum
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
    MOCK_STATS.propertyWrites += 1
    if key == "Parent" then
        local old = rawget(self, "_props").Parent
        if old then
            local children = rawget(old, "_children")
            local at = table.find(children, self)
            if at then table.remove(children, at) end
        end
        if value then table.insert(rawget(value, "_children"), self) end
    end
    local id = rawget(self, "_attributes").DatakyFXNodeId or rawget(self, "Name")
    if key == "Enabled" and rawget(self, "_props").Enabled ~= value then
        record("ENABLED", id, string.format("%.3f", NOW), tostring(value))
    elseif key == "Position" and typeof(value) == "Vector3" then
        record("POSITION", id, string.format("%.3f", NOW), string.format("%.3f %.3f %.3f", value.X, value.Y, value.Z))
    end
    rawget(self, "_props")[key] = value
    if key == "CFrame" then rawget(self, "_props").Position = value.Position end
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
function methods.IsA(self, className)
    return (className == "PVInstance" and (self.ClassName == "Model" or self.ClassName == "Part" or self.ClassName == "MeshPart"))
        or (className == "BasePart" and (self.ClassName == "Part" or self.ClassName == "MeshPart"))
        or (className == "Attachment" and self.ClassName == "Bone") or self.ClassName == className
end
function methods.GetPivot(self) return rawget(self, "_pivot") or CFrame.new(0, 0, 0) end
function methods.Emit(self, count) record("EMIT", rawget(self, "_attributes").DatakyFXNodeId, string.format("%.3f", NOW), tostring(count)) end
function methods.Clear(self) end
function methods.Destroy(self)
    record("DESTROY", rawget(self, "Name"))
    for _, child in ipairs(self:GetChildren()) do child:Destroy() end
    self.Parent = nil
    rawset(self, "_destroyed", true)
end
function methods.Clone(self)
    MOCK_STATS.cloneCalls += 1
    local remap = {}
    local function cloneTree(original, parent)
        local object = setmetatable({Name=original.Name, _props={}, _attributes=table.clone(rawget(original,"_attributes")), _children={}},InstanceMt)
        remap[original] = object
        local properties = rawget(object,"_props")
        for key,value in pairs(rawget(original,"_props")) do if key ~= "Parent" then properties[key] = value end end
        properties.Parent = parent
        for _,child in ipairs(rawget(original,"_children")) do table.insert(rawget(object,"_children"),cloneTree(child,object)) end
        return object
    end
    local out = cloneTree(self,nil)
    for _,object in pairs(remap) do
        for key,value in pairs(rawget(object,"_props")) do
            if remap[value] then rawget(object,"_props")[key] = remap[value] end
        end
    end
    return out
end
function methods.FindFirstChild(self, name)
    for _, child in ipairs(rawget(self, "_children")) do if rawget(child, "Name") == name then return child end end
    return nil
end

function MakeInstance(className, name, attributes, parent)
    local object = setmetatable({Name = name, _props = {ClassName = className, Name = name, Enabled = true}, _attributes = attributes or {}, _children = {}}, InstanceMt)
    if className == "ParticleEmitter" then
        local props = rawget(object, "_props")
        props.TimeScale, props.Rate, props.Lifetime = 1, 20, NumberRange.new(5, 10)
        props.Size, props.Speed, props.Acceleration = NumberSequence.new({NumberSequenceKeypoint.new(0,1,0), NumberSequenceKeypoint.new(1,1,0)}), NumberRange.new(5), Vector3.zero
    elseif className == "Trail" then rawget(object, "_props").Lifetime = 2
    elseif className == "Part" or className == "MeshPart" then rawget(object, "_props").Size = Vector3.new(4,1,2)
    elseif className:match("Light$") then rawget(object, "_props").Range = 8 end
    if parent then object.Parent = parent end
    return object
end

Instance = {new = function(className) MOCK_STATS.newCalls += 1; return MakeInstance(className, className) end}
Content = {fromUri=function(uri) return uri end}
local heartbeats = {}
local Workspace = MakeInstance("Workspace", "Workspace")
local services = {
    Workspace = Workspace,
    RunService = {Heartbeat = {Connect = function(_, fn)
        local entry = {callback=fn, connected=true}
        table.insert(heartbeats, entry)
        return {Disconnect=function() entry.connected=false end}
    end}},
    AssetService = {CreateMeshPartAsync=function(_, uri) local mesh=MakeInstance("MeshPart", "MeshPart"); mesh.MeshId=uri; return mesh end},
    ContentProvider = {calls={}, PreloadAsync=function(self, textures) table.insert(self.calls,table.clone(textures)) end},
}
game = {GetService = function(_, name) return services[name] end}
workspace = Workspace

local deferred = {}
task = {defer=function(callback, ...) table.insert(deferred,{callback=callback,args={...}}) end}
function FlushDeferred()
    local pending = deferred
    deferred = {}
    for _,job in ipairs(pending) do
        local thread = coroutine.create(job.callback)
        local ok,message = coroutine.resume(thread,table.unpack(job.args))
        assert(ok,message)
    end
end

function Step(dt)
    NOW += dt
    for _, entry in ipairs(table.clone(heartbeats)) do if entry.connected then entry.callback(dt) end end
    FlushDeferred()
end
function Dump()
    for _, line in ipairs(EVENTS) do print(line) end
end
