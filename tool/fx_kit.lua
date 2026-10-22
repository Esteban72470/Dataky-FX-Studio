-- Dataky FX Studio: independent, client-safe recipe instances.
-- play never yields. MeshParts must be prepared with FX.preload(recipe) first.
-- Recipe tables are immutable after first use: deep-copy a recipe before editing it.
-- Validation, decoding and a lazy instance template are cached with weak recipe keys.
-- Native Trail histories cannot be frozen by Roblox; freeze pauses their timeline only.
local Workspace = game:GetService("Workspace")
local RunService = game:GetService("RunService")
local AssetService = game:GetService("AssetService")
local ContentProvider = game:GetService("ContentProvider")
local FX = {}
local MAX_NODES = 400

local function extend(a, b)
    local out = {}
    for k, v in pairs(a) do out[k] = v end
    for k, v in pairs(b or {}) do out[k] = v end
    return out
end

local part = {
    Position="Vector3", Orientation="Vector3", Size="Vector3", Color="Color3",
    Transparency="number", Reflectance="number", Material="Enum.Material",
    Anchored="boolean", CanCollide="boolean", CanTouch="boolean", CanQuery="boolean",
    CastShadow="boolean", Massless="boolean", MaterialVariant="string",
}
local light = {Color="Color3", Brightness="number", Range="number", Shadows="boolean", Enabled="boolean"}
local schema = {
    Folder = {}, Model = {},
    Part = extend(part, {Shape="Enum.PartType", TopSurface="Enum.SurfaceType", BottomSurface="Enum.SurfaceType"}),
    MeshPart = extend(part, {MeshId="content", TextureID="content", DoubleSided="boolean", RenderFidelity="Enum.RenderFidelity"}),
    SpecialMesh = {MeshId="content", TextureId="content", MeshType="Enum.MeshType", Scale="Vector3", Offset="Vector3", VertexColor="Vector3"},
    Attachment = {Position="Vector3", Orientation="Vector3", Axis="Vector3", SecondaryAxis="Vector3", Visible="boolean"},
    ParticleEmitter = {
        Texture="content", Color="ColorSequence", Size="NumberSequence", Transparency="NumberSequence",
        Lifetime="NumberRange", Speed="NumberRange", Rate="number", Rotation="NumberRange", RotSpeed="NumberRange",
        Acceleration="Vector3", Drag="number", SpreadAngle="Vector2", EmissionDirection="Enum.NormalId",
        Orientation="Enum.ParticleOrientation", LightEmission="number", LightInfluence="number", Brightness="number",
        ZOffset="number", VelocityInheritance="number", LockedToPart="boolean", TimeScale="number", Squash="NumberSequence",
        Shape="Enum.ParticleEmitterShape", ShapeStyle="Enum.ParticleEmitterShapeStyle", ShapeInOut="Enum.ParticleEmitterShapeInOut",
        ShapePartial="number", FlipbookLayout="Enum.ParticleFlipbookLayout", FlipbookMode="Enum.ParticleFlipbookMode",
        FlipbookFramerate="NumberRange", FlipbookStartRandom="boolean", FlipbookBlendFrames="boolean",
        FlipbookSizeX="number", FlipbookSizeY="number", WindAffectsDrag="boolean", Enabled="boolean",
    },
    Beam = {
        Attachment0="reference", Attachment1="reference", Color="ColorSequence", Transparency="NumberSequence",
        Texture="content", TextureLength="number", TextureSpeed="number", TextureMode="Enum.TextureMode",
        Width0="number", Width1="number", CurveSize0="number", CurveSize1="number", Segments="number",
        FaceCamera="boolean", LightEmission="number", LightInfluence="number", Brightness="number", Enabled="boolean", ZOffset="number",
    },
    Trail = {
        Attachment0="reference", Attachment1="reference", Color="ColorSequence", Transparency="NumberSequence",
        Texture="content", TextureLength="number", TextureMode="Enum.TextureMode", Lifetime="number", MinLength="number",
        MaxLength="number", WidthScale="NumberSequence", FaceCamera="boolean", LightEmission="number", LightInfluence="number",
        Brightness="number", Enabled="boolean",
    },
    PointLight = extend(light),
    SpotLight = extend(light, {Angle="number", Face="Enum.NormalId"}),
    SurfaceLight = extend(light, {Angle="number", Face="Enum.NormalId"}),
}

local function fail(message)
    error("Dataky FX: " .. message, 0)
end

local function finite(v, where)
    if type(v) ~= "number" or v ~= v or v == math.huge or v == -math.huge then
        fail(where .. " doit être un nombre fini")
    end
    return v
end

local function vector(v, dimensions, where)
    if type(v) ~= "table" or #v ~= dimensions then fail(where .. " doit avoir " .. dimensions .. " composantes") end
    for i = 1, dimensions do finite(v[i], where .. "[" .. i .. "]") end
    if dimensions == 2 then return Vector2.new(v[1], v[2]) end
    return Vector3.new(v[1], v[2], v[3])
end

local function color(v, where)
    vector(v, 3, where)
    for _, n in ipairs(v) do if n < 0 or n > 1 then fail(where .. " RGB doit être entre 0 et 1") end end
    return Color3.new(v[1], v[2], v[3])
end

local function content(v, where)
    if type(v) == "number" then
        finite(v, where)
        if v <= 0 or v % 1 ~= 0 then fail(where .. " : ID invalide") end
        return "rbxassetid://" .. string.format("%.0f", v)
    end
    if type(v) ~= "string" then fail(where .. " doit être une URI Roblox") end
    if v == "" then return "" end
    if v:match("^%d+$") then return "rbxassetid://" .. v end
    if v:match("^rbxassetid://%d+$") or v:match("^rbxasset://[%w_/%-%.]+$") then return v end
    if v:match("^https?://www%.roblox%.com/asset/?%?id=%d+$") or v:match("^https?://roblox%.com/asset/?%?id=%d+$") then
        return "rbxassetid://" .. v:match("id=(%d+)$")
    end
    fail(where .. " : URI non prise en charge (rbxassetid://ID ou rbxasset://...)")
end

local function decode(kind, value, where)
    if kind == "number" then return finite(value, where) end
    if kind == "string" then
        if type(value) ~= "string" or #value > 2048 then fail(where .. " doit être un texte") end
        return value
    end
    if kind == "boolean" then
        if type(value) ~= "boolean" then fail(where .. " doit être true ou false") end
        return value
    end
    if kind == "Vector2" then return vector(value, 2, where) end
    if kind == "Vector3" then return vector(value, 3, where) end
    if kind == "Color3" then return color(value, where) end
    if kind == "content" then return content(value, where) end
    if kind == "reference" then
        if type(value) ~= "string" or value == "" then fail(where .. " doit désigner un Attachment") end
        return value
    end
    if kind == "NumberRange" then
        if type(value) ~= "table" or #value ~= 2 then fail(where .. " doit être [min,max]") end
        local lo, hi = finite(value[1], where), finite(value[2], where)
        if lo > hi then fail(where .. " : min dépasse max") end
        return NumberRange.new(lo, hi)
    end
    if kind == "NumberSequence" or kind == "ColorSequence" then
        if type(value) ~= "table" or #value < 2 or #value > 20 then fail(where .. " : il faut 2 à 20 points") end
        local points, last = {}, -1
        for i, point in ipairs(value) do
            if type(point) ~= "table" then fail(where .. " : point invalide") end
            local t = finite(point.time ~= nil and point.time or point[1], where .. ".time")
            if t < 0 or t > 1 or t <= last then fail(where .. " : temps croissants entre 0 et 1 requis") end
            last = t
            if kind == "NumberSequence" then
                local envelope = finite(point.envelope or point[3] or 0, where .. ".envelope")
                if envelope < 0 then fail(where .. " : enveloppe négative") end
                table.insert(points, NumberSequenceKeypoint.new(t, finite(point.value ~= nil and point.value or point[2], where .. ".value"), envelope))
            else
                table.insert(points, ColorSequenceKeypoint.new(t, color(point.value or point[2], where .. ".value")))
            end
            if i == 1 and t ~= 0 then fail(where .. " : premier temps doit être 0") end
        end
        if last ~= 1 then fail(where .. " : dernier temps doit être 1") end
        return kind == "NumberSequence" and NumberSequence.new(points) or ColorSequence.new(points)
    end
    local enumName = kind:match("^Enum%.(.+)$")
    if enumName then
        if type(value) ~= "string" then fail(where .. " doit être un nom d'enum") end
        local short = value:match("([%w_]+)$")
        local ok, item = pcall(function() return Enum[enumName][short] end)
        if not ok or not item then fail(where .. " : valeur " .. tostring(value) .. " inconnue pour " .. enumName) end
        return item
    end
    fail(where .. " : codec inconnu " .. tostring(kind))
end

local function setProperty(object, property, value, label)
    local ok, message = pcall(function() object[property] = value end)
    if not ok then fail(label .. "." .. property .. " : " .. tostring(message)) end
end

local function orderedProperties(properties)
    local keys = {}
    for key in pairs(properties) do table.insert(keys, key) end
    -- Orientation sets the axes; explicit axes then refine that orientation.
    -- The layout is applied after custom grid dimensions, matching the chosen mode.
    local priority = {Orientation=10, Axis=11, SecondaryAxis=12, FlipbookLayout=20}
    table.sort(keys, function(a,b)
        local pa, pb = priority[a] or 0, priority[b] or 0
        return pa == pb and a < b or pa < pb
    end)
    return keys
end

local function isBaseClass(class)
    return class == "Part" or class == "MeshPart"
end

local function isSwitchClass(class)
    return class == "ParticleEmitter" or class == "Beam" or class == "Trail" or class == "PointLight" or class == "SpotLight" or class == "SurfaceLight"
end

local function validate(data)
    if type(data) ~= "table" or data.version ~= 1 then fail("projet version 1 attendu") end
    if data.name ~= nil and type(data.name) ~= "string" then fail("name doit être un texte") end
    if type(data.nodes) ~= "table" or #data.nodes > MAX_NODES then fail("nodes doit contenir au plus " .. MAX_NODES .. " objets") end
    local duration = finite(data.duration or 3, "duration")
    if duration <= 0 or duration > 600 then fail("duration doit être entre 0 et 600 secondes") end
    if data.loop ~= nil and type(data.loop) ~= "boolean" then fail("loop doit être un booléen") end
    local byId, normalized, decodedTracks = {}, {}, {}
    for _, node in ipairs(data.nodes) do
        if type(node) ~= "table" or type(node.id) ~= "string" or node.id == "" or #node.id > 120 then fail("id de node invalide") end
        if byId[node.id] then fail("id dupliqué " .. node.id) end
        if not schema[node.class] then fail("classe interdite " .. tostring(node.class)) end
        if node.name ~= nil and type(node.name) ~= "string" then fail(node.id .. ".name doit être un texte") end
        local decoded = {}
        for property, value in pairs(node.properties or {}) do
            local kind = schema[node.class][property]
            if not kind then fail(node.id .. "." .. tostring(property) .. " : propriété non prise en charge") end
            decoded[property] = decode(kind, value, node.id .. "." .. property)
        end
        if node.class == "Attachment" and decoded.Orientation and (decoded.Axis or decoded.SecondaryAxis) then
            fail(node.id .. " : utilisez Orientation ou Axis/SecondaryAxis ; ces propriétés règlent la même rotation")
        end
        local timing = node.timing
        if timing ~= nil then
            if not isSwitchClass(node.class) or type(timing) ~= "table" then fail(node.id .. " : timing exige un émetteur, beam, trail ou lumière") end
            local start = finite(timing.start or 0, node.id .. ".timing.start")
            local span = finite(timing.duration or duration, node.id .. ".timing.duration")
            if start < 0 or span < 0 then fail(node.id .. " : timing négatif") end
            if timing.mode ~= "burst" and timing.mode ~= "continuous" then fail(node.id .. " : mode burst ou continuous attendu") end
            if timing.mode == "burst" and node.class ~= "ParticleEmitter" then fail(node.id .. " : burst réservé aux particules") end
            local count = finite(timing.count or 30, node.id .. ".timing.count")
            if count < 0 or count > 10000 or count % 1 ~= 0 then fail(node.id .. " : count entier entre 0 et 10000 requis") end
            timing = {start=start, duration=span, mode=timing.mode, count=count}
        end
        local item = {id=node.id, class=node.class, name=node.name or node.class, parent=node.parent, properties=decoded, timing=timing}
        byId[node.id] = item
        table.insert(normalized, item)
    end
    for _, node in ipairs(normalized) do
        local parent = node.parent ~= nil and byId[node.parent] or nil
        if node.parent ~= nil and not parent then fail(node.id .. " : parent introuvable " .. tostring(node.parent)) end
        local visited, cursor = {}, node
        while cursor do
            if visited[cursor.id] then fail(node.id .. " : cycle dans les parents") end
            visited[cursor.id] = true
            cursor = cursor.parent ~= nil and byId[cursor.parent] or nil
        end
        if node.class == "Attachment" and not (parent and (isBaseClass(parent.class) or parent.class == "Attachment")) then
            fail(node.id .. " : Attachment doit être dans un Part, MeshPart ou Attachment")
        end
        if node.class == "ParticleEmitter" and not (parent and (isBaseClass(parent.class) or parent.class == "Attachment")) then
            fail(node.id .. " : ParticleEmitter doit être dans un Part, MeshPart ou Attachment")
        end
        if node.class == "SpecialMesh" and not (parent and parent.class == "Part") then fail(node.id .. " : SpecialMesh doit être dans un Part") end
        if node.class:match("Light$") and not (parent and (isBaseClass(parent.class) or parent.class == "Attachment")) then fail(node.id .. " : Light doit être dans un Part ou Attachment") end
        if node.class == "Folder" or node.class == "Model" or isBaseClass(node.class) or node.class == "Beam" or node.class == "Trail" then
            local validParent = not parent or parent.class == "Folder" or parent.class == "Model" or isBaseClass(parent.class)
                or ((node.class == "Beam" or node.class == "Trail") and parent.class == "Attachment")
            if not validParent then fail(node.id .. " : parent incompatible avec " .. node.class) end
        end
        for property, value in pairs(node.properties) do
            if schema[node.class][property] == "reference" then
                if not byId[value] or byId[value].class ~= "Attachment" then fail(node.id .. "." .. property .. " : Attachment interne introuvable " .. value) end
            end
        end
    end
    for _, track in ipairs(data.animations or {}) do
        local node = byId[track.node]
        if not node then fail("animation : node introuvable " .. tostring(track.node)) end
        local kind = schema[node.class][track.property]
        if not kind or kind == "reference" or track.property == "MeshId" then fail(node.id .. ": propriété non animable " .. tostring(track.property)) end
        if kind == "NumberSequence" or kind == "ColorSequence" or kind == "content" or kind == "string" then fail(node.id .. ": animation temporelle non prise en charge pour " .. track.property) end
        if type(track.keyframes) ~= "table" or #track.keyframes < 1 or #track.keyframes > 1000 then fail(node.id .. ": keyframes invalides") end
        local points, last = {}, -1
        for _, key in ipairs(track.keyframes) do
            local t = finite(key.time, node.id .. ".animation.time")
            if t < 0 or t <= last then fail(node.id .. ": temps de keyframes strictement croissants requis") end
            last = t
            table.insert(points, {time=t, value=decode(kind, key.value, node.id .. ".animation." .. track.property)})
        end
        table.insert(decodedTracks, {node=node.id, property=track.property, kind=kind, keyframes=points})
    end
    return normalized, decodedTracks, duration
end

local active, meshCache = {}, {}
local connection, frozen, nextId = nil, false, 0
local scaled = {
    Part={Position=true, Size=true}, MeshPart={Position=true, Size=true},
    Attachment={Position=true}, SpecialMesh={Scale=true, Offset=true},
    ParticleEmitter={Size=true, Speed=true, Acceleration=true},
    PointLight={Range=true}, SpotLight={Range=true}, SurfaceLight={Range=true},
}

local function scaleValue(value, factor)
    local kind = typeof(value)
    if factor == 1 then return value end
    if kind == "number" or kind == "Vector3" or kind == "Vector2" then return value * factor end
    if kind == "NumberRange" then return NumberRange.new(value.Min * factor, value.Max * factor) end
    if kind == "NumberSequence" then
        local keys = {}
        for _, point in ipairs(value.Keypoints) do
            table.insert(keys, NumberSequenceKeypoint.new(point.Time, point.Value * factor, point.Envelope * factor))
        end
        return NumberSequence.new(keys)
    end
    fail("scaleWith exige un nombre, un vecteur, un NumberRange ou un NumberSequence")
end

local function positive(value, label, zero)
    finite(value, label)
    if value < 0 or (not zero and value == 0) then fail(label .. " doit être positif") end
    return value
end

local recipeCache = setmetatable({}, {__mode="k"})

local function compiled(data)
    if type(data) ~= "table" then fail("recette table attendue") end
    local cached = recipeCache[data]
    if cached then return cached end
    local nodes, tracks, duration = validate(data)
    local entry = {nodes=nodes, specs={}, tracks={}, duration=duration, name=data.name or "Effect", defaults={}, links={}}
    for name, definition in pairs(data.params or {}) do
        if type(name) ~= "string" then fail("un nom de paramètre doit être un texte") end
        if type(definition) ~= "table" then fail("params." .. tostring(name) .. " doit définir default") end
        entry.defaults[name] = positive(definition.default, "params." .. tostring(name) .. ".default")
    end
    for i, node in ipairs(nodes) do
        entry.specs[node.id] = node
        node.order = orderedProperties(node.properties)
        node.dimensions = extend(scaled[node.class] or {})
        local links = {}
        for property, parameter in pairs(data.nodes[i].scaleWith or {}) do
            local kind = schema[node.class][property]
            if not (kind == "number" or kind == "Vector3" or kind == "Vector2" or kind == "NumberRange" or kind == "NumberSequence") then
                fail(node.id .. ".scaleWith." .. tostring(property) .. " n'est pas une propriété dimensionnelle")
            end
            if not entry.defaults[parameter] then fail(node.id .. ".scaleWith : paramètre inconnu " .. tostring(parameter)) end
            links[property], node.dimensions[property] = parameter, true
        end
        entry.links[node.id] = links
    end
    for _, track in ipairs(tracks) do
        local spec = entry.specs[track.node]
        -- Gameplay owns carrier movement and visibility; these are preview tracks.
        if not (isBaseClass(spec.class) and (track.property == "Position" or track.property == "Transparency")) then
            table.insert(entry.tracks, track)
        end
    end
    -- The value contains only decoded snapshots, never the original weak key.
    recipeCache[data] = entry
    return entry
end

local function factors(entry, opts)
    local ratios = {}
    for name, value in pairs(opts.params or {}) do
        local baseline = entry.defaults[name]
        if not baseline then fail("paramètre inconnu " .. tostring(name)) end
        ratios[name] = positive(value, "options.params." .. name, true) / baseline
    end
    return ratios
end

local function meshKey(node)
    return tostring(node.properties.MeshId or "") .. "|" .. tostring(node.properties.RenderFidelity or "Automatic")
end

-- This optional preparation may yield; play only clones the prepared templates.
function FX.preload(data)
    local nodes = compiled(data).nodes
    for _, node in ipairs(nodes) do
        if node.class == "MeshPart" then
            local key = meshKey(node)
            if not meshCache[key] then
                if not node.properties.MeshId or node.properties.MeshId == "" then fail(node.id .. ".MeshId est requis") end
                local settings = {RenderFidelity=node.properties.RenderFidelity or Enum.RenderFidelity.Automatic}
                local template = AssetService:CreateMeshPartAsync(Content.fromUri(node.properties.MeshId), settings)
                template.Parent = nil
                meshCache[key] = template
            end
        end
    end
end

local function templateFor(entry)
    if entry.template then return entry.template end
    local root, objects = Instance.new("Folder"), {}
    root.Name = "DatakyFXTemplate"
    root:SetAttribute("DatakyFXKitOwned", true)
    local ok, message = pcall(function()
        for _, node in ipairs(entry.nodes) do
            local object
            if node.class == "MeshPart" then
                local template = meshCache[meshKey(node)]
                if not template then fail(node.id .. " : appelez FX.preload(recipe) avant play pour préparer le MeshPart") end
                object = template:Clone()
            else object = Instance.new(node.class) end
            object.Name = node.name
            object:SetAttribute("DatakyFXNodeId", node.id)
            object.Parent = root
            objects[node.id] = object
            if isBaseClass(node.class) then
                object.Anchored, object.CanCollide, object.CanTouch, object.CanQuery = true, false, false, false
                object.Transparency, object.CastShadow, object.Massless = 1, false, true
            end
            if isSwitchClass(node.class) then object.Enabled = false end
            for _, property in ipairs(node.order) do
                local kind = schema[node.class][property]
                if kind ~= "reference" and property ~= "Enabled"
                    and not (isBaseClass(node.class) and (property == "Position" or property == "Orientation"))
                    and not (node.class == "MeshPart" and (property == "MeshId" or property == "RenderFidelity")) then
                    setProperty(object, property, node.properties[property], node.id)
                end
            end
            node.baseDimensions = {}
            for property in pairs(node.dimensions) do
                if not (isBaseClass(node.class) and property == "Position") then node.baseDimensions[property] = object[property] end
            end
            if isBaseClass(node.class) then
                node.position = node.properties.Position or Vector3.zero
                local o = node.properties.Orientation or Vector3.zero
                node.rotation = CFrame.fromOrientation(math.rad(o.X), math.rad(o.Y), math.rad(o.Z))
                node.offset = CFrame.new(node.position) * node.rotation
            end
        end
        for _, node in ipairs(entry.nodes) do
            local object = objects[node.id]
            object.Parent = node.parent and objects[node.parent] or root
            for property, value in pairs(node.properties) do
                if schema[node.class][property] == "reference" then object[property] = objects[value] end
            end
        end
    end)
    if not ok then root:Destroy(); fail(tostring(message)) end
    entry.template = root
    return root
end

-- Optional eager preparation. MeshParts still require the yielding preload first.
-- play also prepares lazily on first use; subsequent plays only clone/place/start.
function FX.prepare(data)
    templateFor(compiled(data))
    return data
end

function FX.listTextures(data)
    if type(data) ~= "table" then fail("preloadTextures exige une recette ou bibliothèque") end
    local found = {}
    local function collect(recipe)
        for _, node in ipairs(compiled(recipe).nodes) do
            local key = (node.class == "ParticleEmitter" or node.class == "Beam" or node.class == "Trail") and "Texture"
                or (node.class == "MeshPart" and "TextureID") or (node.class == "SpecialMesh" and "TextureId")
            local uri = key and node.properties[key]
            if uri and uri ~= "" then found[uri] = true end
        end
    end
    -- Filename keys such as "version" and "nodes" are legal library recipes.
    local recipeShape = (data.version ~= nil and type(data.version) ~= "table")
        or (data.nodes ~= nil and (type(data.nodes) ~= "table" or data.nodes.version == nil))
    if recipeShape then collect(data)
    else
        for _, recipe in pairs(data) do
            if type(recipe) == "table" and recipe.version ~= nil then collect(recipe) end
        end
    end
    local textures = {}
    for uri in pairs(found) do table.insert(textures, uri) end
    table.sort(textures)
    return textures
end

-- Startup API: ContentProvider may yield here, never in play/prepare.
function FX.preloadTextures(data)
    local textures = FX.listTextures(data)
    if #textures > 0 then ContentProvider:PreloadAsync(textures) end
    return textures
end

local function lowQuality(quality)
    if quality == "Low" then return true end
    if quality == "High" then return false end
    if quality ~= nil and quality ~= "Auto" then fail("quality : Auto, Low ou High attendu") end
    local ok, level = pcall(function() return UserSettings().GameSettings.SavedQualityLevel.Value end)
    return ok and type(level) == "number" and level <= 3
end

local function lerp(a, b, alpha)
    local kind = typeof(a)
    if kind == "number" then return a + (b - a) * alpha end
    if kind == "Vector3" or kind == "Vector2" or kind == "Color3" then return a:Lerp(b, alpha) end
    if kind == "NumberRange" then return NumberRange.new(a.Min + (b.Min - a.Min) * alpha, a.Max + (b.Max - a.Max) * alpha) end
    return alpha >= 1 and b or a
end

local function sample(track, time)
    local keys = track.keyframes
    if time <= keys[1].time then return keys[1].value end
    for i = 2, #keys do
        if time < keys[i].time then
            local a, b = keys[i - 1], keys[i]
            return lerp(a.value, b.value, (time - a.time) / (b.time - a.time))
        end
    end
    return keys[#keys].value
end

local function followFrame(follow)
    if type(follow) == "function" then return follow() end
    if typeof(follow) ~= "Instance" or not follow.Parent then return nil end
    if follow:IsA("Bone") then return follow.TransformedWorldCFrame end
    if follow:IsA("Attachment") then return follow.WorldCFrame end
    if follow:IsA("BasePart") then return follow.CFrame end
    fail("follow : fonction, Attachment, Bone ou BasePart attendu")
end

local function defaultParent()
    local parent = Workspace:FindFirstChild("DatakyFX")
    if parent then return parent end
    parent = Instance.new("Folder")
    parent.Name = "DatakyFX"
    parent:SetAttribute("DatakyFXKitContainer", true)
    parent.Parent = Workspace
    return parent
end

local function disconnectIfIdle()
    if next(active) == nil and connection then connection:Disconnect(); connection = nil end
end

local function finish(handle)
    if handle.stopped then return end
    handle.stopped = true
    active[handle] = nil
    handle.root:Destroy()
    local parent = handle.parent
    if parent and parent:GetAttribute("DatakyFXKitContainer") == true and #parent:GetChildren() == 0 then parent:Destroy() end
    disconnectIfIdle()
    local callback = handle.onFinished
    handle.onFinished = nil
    if callback then
        -- User code may yield. Deferring it keeps play and Stop non-yielding.
        task.defer(function()
            local ok, message = pcall(callback, handle)
            if not ok then warn("Dataky FX Kit onFinished : " .. tostring(message)) end
        end)
    end
end

local function lifetime(object, class, timeScaleOverride)
    if class == "Trail" then return object.Lifetime or 2 end
    if class == "ParticleEmitter" then
        local span = object.Lifetime and object.Lifetime.Max or 5
        local timeScale = timeScaleOverride or object.TimeScale or 1
        -- An authored TimeScale=0 cannot expire naturally; keep cleanup bounded.
        return timeScale > 0 and span / timeScale or span
    end
    return 0
end

local function place(handle, cf)
    if typeof(cf) ~= "CFrame" then fail("Move exige une CFrame") end
    handle.cf = cf
    for _, item in ipairs(handle.parts) do item.object.CFrame = cf * item.offset end
    for _, item in ipairs(handle.accelerations) do item.object.Acceleration = cf:VectorToWorldSpace(item.value) end
end

local function remainingLife(handle, id)
    local saved = handle.frozenProperties and handle.frozenProperties[id]
    return lifetime(handle.objects[id], handle.specs[id].class, saved and saved.TimeScale)
end

local function update(handle, dt)
    if handle.stopped then return end
    if not handle.root.Parent then finish(handle); return end
    handle.age += dt
    if not handle.released then handle.time += dt * handle.speed end
    local t = math.min(handle.time, handle.duration)
    if dt > 0 and handle.follow and not handle.released then
        local cf = followFrame(handle.follow)
        if cf then place(handle, cf) else handle:Release() end
    end
    local animatedEnabled = {}
    for _, track in ipairs(handle.tracks) do
        local object, value = handle.objects[track.node], sample(track, t)
        if track.property == "Enabled" then animatedEnabled[track.node] = value
        elseif not handle.released then
            value = scaleValue(value, handle.factor(track.node, track.property))
            if track.property == "Orientation" and isBaseClass(handle.specs[track.node].class) then
                local item = handle.partById[track.node]
                item.offset = CFrame.new(item.position) * CFrame.fromOrientation(math.rad(value.X), math.rad(value.Y), math.rad(value.Z))
                object.CFrame = handle.cf * item.offset
            elseif track.property == "Acceleration" and handle.specs[track.node].class == "ParticleEmitter" then
                handle.accelerationById[track.node].value = value
                value = handle.cf:VectorToWorldSpace(value)
                setProperty(object, track.property, value, track.node)
            else
                setProperty(object, track.property, value, track.node)
            end
        end
    end
    local anyOn = false
    for id, spec in pairs(handle.specs) do
        if isSwitchClass(spec.class) then
            local object, timing = handle.objects[id], spec.timing
            local allowed = spec.properties.Enabled ~= false and animatedEnabled[id] ~= false and not handle.released
            local on = false
            if timing and timing.mode == "burst" then
                if not handle.fired[id] and t >= timing.start then
                    handle.fired[id] = true
                    local count = math.floor(timing.count * handle.quality + 0.5)
                    if allowed and count > 0 then
                        object:Emit(count)
                        handle.expires = math.max(handle.expires, handle.age + remainingLife(handle, id))
                    end
                end
            else
                local start = timing and timing.start or 0
                local endTime = timing and timing.start + timing.duration or handle.duration
                on = allowed and t >= start and (handle.hold or handle.time < endTime)
            end
            -- The previous enabled interval may have emitted just before this frame.
            if on or object.Enabled then
                handle.expires = math.max(handle.expires, handle.age + remainingLife(handle, id))
            end
            object.Enabled = on
            anyOn = anyOn or on
        end
    end
    if not anyOn and (handle.released or handle.time >= handle.duration) and handle.age >= handle.expires then
        finish(handle)
    end
end

local function connect()
    if connection then return end
    connection = RunService.Heartbeat:Connect(function(dt)
        if frozen then return end
        for handle in pairs(active) do
            local ok, message = pcall(update, handle, dt)
            if not ok then finish(handle); warn("Dataky FX Kit : " .. tostring(message)) end
        end
    end)
end

function FX.play(data, cf, opts)
    opts = opts or {}
    cf = cf or CFrame.new()
    if typeof(cf) ~= "CFrame" then fail("play exige une CFrame") end
    local scale = positive(opts.scale or 1, "options.scale")
    local speed = positive(opts.speed or 1, "options.speed")
    local entry = compiled(data)
    local ratios, q = factors(entry, opts), lowQuality(opts.quality) and 0.6 or 1
    if opts.parent ~= nil and typeof(opts.parent) ~= "Instance" then fail("options.parent doit être une Instance") end
    if opts.onFinished ~= nil and type(opts.onFinished) ~= "function" then fail("options.onFinished doit être une fonction") end
    local handle = {objects={}, specs=entry.specs, parts={}, partById={}, accelerations={}, accelerationById={}, tracks=entry.tracks, fired={},
        duration=entry.duration, age=0, time=0, expires=0, speed=speed, cf=cf, quality=q, hold=false, follow=opts.follow, onFinished=opts.onFinished}
    function handle.factor(id, property)
        local spec = handle.specs[id]
        local parameter = entry.links[id][property]
        return ((scaled[spec.class] or {})[property] and scale or 1) * (parameter and ratios[parameter] or 1)
    end
    handle.root = templateFor(entry):Clone()
    nextId += 1
    handle.root.Name = entry.name .. "_" .. tostring(nextId)
    local ok, message = pcall(function()
        for _, object in ipairs(handle.root:GetDescendants()) do
            handle.objects[object:GetAttribute("DatakyFXNodeId")] = object
        end
        for _, node in ipairs(entry.nodes) do
            local object = handle.objects[node.id]
            if opts.hold == true and isSwitchClass(node.class) and node.properties.Enabled ~= false
                and (not node.timing or node.timing.mode == "continuous") then handle.hold = true end
            if scale ~= 1 or next(ratios) ~= nil then
                for property, value in pairs(node.baseDimensions) do
                    local factor = handle.factor(node.id, property)
                    if factor ~= 1 then setProperty(object, property, scaleValue(value, factor), node.id) end
                end
            end
            if isBaseClass(node.class) then
                local factor = handle.factor(node.id, "Position")
                local position = factor == 1 and node.position or node.position * factor
                local offset = factor == 1 and node.offset or CFrame.new(position) * node.rotation
                local item = {object=object, position=position, offset=offset}
                table.insert(handle.parts, item)
                handle.partById[node.id] = item
            elseif node.class == "ParticleEmitter" then
                local acceleration = {object=object, value=object.Acceleration or Vector3.zero}
                table.insert(handle.accelerations, acceleration)
                handle.accelerationById[node.id] = acceleration
            end
        end
        place(handle, cf)
    end)
    if not ok then handle.root:Destroy(); fail(tostring(message)) end
    function handle:Release(options)
        if self.stopped then return end
        if options and options.hideParts == true then
            for _, item in ipairs(self.parts) do item.object.Transparency = 1 end
        end
        if self.released then return end
        self.released = true
        self.follow = nil
        for id, spec in pairs(self.specs) do
            if isSwitchClass(spec.class) then
                local object = self.objects[id]
                if object.Enabled then self.expires = math.max(self.expires, self.age + remainingLife(self, id)) end
                object.Enabled = false
            end
        end
    end
    function handle:Stop() finish(self) end
    function handle:Move(at) if not self.stopped then place(self, at) end end
    function handle:Part(id) return not self.stopped and self.objects[id] or nil end
    function handle:SetFollow(target)
        if self.stopped or self.released then return self end
        if target ~= nil and type(target) ~= "function" then
            if typeof(target) ~= "Instance" or not (target:IsA("BasePart") or target:IsA("Attachment")) then
                fail("SetFollow : fonction, Attachment, Bone ou BasePart attendu")
            end
        end
        self.follow = target
        return self
    end
    local started, startError = pcall(function()
        handle.parent = opts.parent or defaultParent()
        handle.root.Parent = handle.parent
        active[handle] = true
        update(handle, 0)
    end)
    if not started then finish(handle); fail(tostring(startError)) end
    if frozen then
        handle.frozenProperties = {}
        for id, spec in pairs(handle.specs) do
            if spec.class == "ParticleEmitter" then
                local object = handle.objects[id]
                handle.frozenProperties[id] = {TimeScale=object.TimeScale, Enabled=object.Enabled}
                object.TimeScale, object.Enabled = 0, false
            elseif spec.class == "Beam" then
                local object = handle.objects[id]
                handle.frozenProperties[id] = {TextureSpeed=object.TextureSpeed}
                object.TextureSpeed = 0
            end
        end
    end
    if not handle.stopped then connect() end
    return handle
end

function FX.freeze()
    if frozen then return end
    frozen = true
    for handle in pairs(active) do
        handle.frozenProperties = {}
        for id, spec in pairs(handle.specs) do
            local object = handle.objects[id]
            if spec.class == "ParticleEmitter" then
                handle.frozenProperties[id] = {TimeScale=object.TimeScale, Enabled=object.Enabled}
                object.TimeScale, object.Enabled = 0, false
            elseif spec.class == "Beam" then
                handle.frozenProperties[id] = {TextureSpeed=object.TextureSpeed}
                object.TextureSpeed = 0
            end
        end
    end
end

function FX.unfreeze()
    if not frozen then return end
    for handle in pairs(active) do
        for id, properties in pairs(handle.frozenProperties or {}) do
            for property, value in pairs(properties) do
                if property ~= "Enabled" or not handle.released then handle.objects[id][property] = value end
            end
        end
        handle.frozenProperties = nil
    end
    frozen = false
end

return FX

