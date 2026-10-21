-- Dataky FX Studio: native Roblox renderer. No project text is executed as code.
-- ModuleScript/command-bar body; returns one independent runtime handle.
local Workspace = game:GetService("Workspace")
local RunService = game:GetService("RunService")
local AssetService = game:GetService("AssetService")
local ContentProvider = game:GetService("ContentProvider")
local Runtime = {}
local OWNED = "DatakyFXOwned"
local PREVIEW_NAME = "__DatakyFXPreview"
local MAX_NODES = 400
local root, project, objects, specs, tracks = nil, nil, {}, {}, {}
local options, origin = {}, Vector3.zero
local connection, cameraConnection, savedCamera = nil, nil, nil
local running, paused, elapsed, generation = false, false, 0, 0
local errors, warnings, fired = {}, {}, {}
local pausedProperties = {}
local activeOptions = nil
local loadingAssets, assetFailures, assetMonitor = false, {}, nil
local assetGeneration = 0
local ASSET_LOAD_TIMEOUT = 15

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
    if v:match("^https?://www%.roblox%.com/asset/%?id=%d+$") or v:match("^https?://roblox%.com/asset/%?id=%d+$") then
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

local function disconnect()
    if connection then connection:Disconnect(); connection = nil end
end

local function restoreCamera()
    if cameraConnection then cameraConnection:Disconnect(); cameraConnection = nil end
    if savedCamera then
        local old = savedCamera
        savedCamera = nil
        if old.camera and old.camera.Parent then
            old.camera.CameraType = old.cameraType
            old.camera.CFrame = old.cframe
            old.camera.Focus = old.focus
            old.camera.FieldOfView = old.fov
        end
    end
end

local function configureCamera(data, opts)
    if opts.camera == false or opts.preview == false then restoreCamera(); return end
    local config = data.camera or {position={10,6,12}, target={0,1,0}}
    local camera = Workspace.CurrentCamera
    if not camera then fail("CurrentCamera introuvable") end
    local position = vector(config.position or {10,6,12}, 3, "camera.position") + origin
    local target = vector(config.target or {0,1,0}, 3, "camera.target") + origin
    if (position-target).Magnitude < 0.001 then fail("camera.position et target doivent différer") end
    local fov = finite(config.fov or 50, "camera.fov")
    if fov < 1 or fov > 120 then fail("camera.fov doit être entre 1 et 120") end
    if not savedCamera then savedCamera = {camera=camera,cameraType=camera.CameraType,cframe=camera.CFrame,focus=camera.Focus,fov=camera.FieldOfView} end
    if cameraConnection then cameraConnection:Disconnect() end
    local cf, focus = CFrame.lookAt(position, target), CFrame.new(target)
    local function updateCamera()
        if Workspace.CurrentCamera == camera and root and root.Parent then
            camera.CameraType = Enum.CameraType.Scriptable
            camera.CFrame = cf
            camera.Focus = focus
            camera.FieldOfView = fov
        end
    end
    updateCamera()
    cameraConnection = RunService.Heartbeat:Connect(updateCamera)
end

local function clearVisuals(clearParticles)
    for id, object in pairs(objects) do
        local spec = specs[id]
        if spec and isSwitchClass(spec.class) then
            object.Enabled = false
            if clearParticles and (spec.class == "ParticleEmitter" or spec.class == "Trail") then object:Clear() end
        end
    end
end

local function cancelAssetMonitor()
    assetGeneration += 1
    local old = assetMonitor
    assetMonitor, loadingAssets = nil, false
    if old then
        old.finished = true
        if old.worker then pcall(task.cancel, old.worker) end
        if old.timeout then pcall(task.cancel, old.timeout) end
    end
end

local function monitorAssets()
    cancelAssetMonitor()
    assetFailures = {}
    local assetProperties = {
        ParticleEmitter={"Texture"}, Beam={"Texture"}, Trail={"Texture"},
        MeshPart={"TextureID"}, SpecialMesh={"MeshId", "TextureId"},
    }
    local entries, uris, byAssetId = {}, {}, {}
    for id, spec in pairs(specs) do
        for _, property in ipairs(assetProperties[spec.class] or {}) do
            local ok, uri = pcall(function() return objects[id][property] end)
            if ok and type(uri) == "string" and uri ~= "" then
                if not entries[uri] then
                    entries[uri] = {uri=uri, references={}}
                    table.insert(uris, uri)
                    local assetId = uri:match("^rbxassetid://(%d+)$") or uri:match("[?&]id=(%d+)")
                    if assetId then byAssetId[assetId] = uri end
                end
                table.insert(entries[uri].references, {node=id, property=property})
            end
        end
    end
    if #uris == 0 then return end
    local state = {ticket=assetGeneration, root=root, finished=false, observed={}, failed={}}
    assetMonitor, loadingAssets = state, true
    local function current()
        return assetMonitor == state and state.ticket == assetGeneration and not state.finished and root == state.root
    end
    local function note(uri, statusName, detail)
        if not current() then return end
        local key = entries[uri] and uri or byAssetId[uri:match("^rbxassetid://(%d+)$") or uri:match("[?&]id=(%d+)") or ""]
        key = key or uri
        state.observed[key] = true
        if statusName ~= "Success" and not state.failed[key] then
            state.failed[key] = true
            local message = "Ressource Roblox indisponible : " .. key .. " (" .. statusName .. ")"
            if detail then message ..= " : " .. tostring(detail) end
            table.insert(assetFailures, {uri=key,status=statusName,message=message,references=entries[key] and entries[key].references or {}})
            table.insert(warnings, message)
        end
    end
    local function statusName(status)
        local ok, name = pcall(function() return status.Name end)
        return ok and tostring(name) or tostring(status)
    end
    local function finish()
        if not current() then return end
        state.finished, loadingAssets = true, false
        if state.timeout then pcall(task.cancel, state.timeout); state.timeout = nil end
    end
    state.timeout = task.delay(ASSET_LOAD_TIMEOUT, function()
        if not current() then return end
        for _, uri in ipairs(uris) do
            if not state.observed[uri] then note(uri, "Timeout", "vérification interrompue après " .. ASSET_LOAD_TIMEOUT .. " secondes") end
        end
        state.finished, loadingAssets = true, false
        state.timeout = nil
        if state.worker then pcall(task.cancel, state.worker); state.worker = nil end
    end)
    state.worker = task.spawn(function()
        local ok, message = pcall(function()
            ContentProvider:PreloadAsync(uris, function(uri, status)
                if current() then note(tostring(uri), statusName(status)) end
            end)
        end)
        if not current() then return end
        for _, uri in ipairs(uris) do
            if not state.observed[uri] then
                if not ok then note(uri, "Error", message)
                else
                    local fetchOk, status = pcall(function() return ContentProvider:GetAssetFetchStatus(uri) end)
                    note(uri, fetchOk and statusName(status) or "Error", fetchOk and nil or status)
                end
            end
        end
        finish()
    end)
end

function Runtime.stop()
    disconnect()
    running, paused, elapsed = false, false, 0
    for id, props in pairs(pausedProperties) do
        if objects[id] then
            for property, value in pairs(props) do objects[id][property] = value end
        end
    end
    pausedProperties = {}
    if root and root.Parent then clearVisuals(true) end
    return Runtime.status()
end

function Runtime.clear()
    generation += 1
    cancelAssetMonitor()
    Runtime.stop()
    restoreCamera()
    if root and root:GetAttribute(OWNED) == true then root:Destroy() end
    root, project, objects, specs, tracks = nil, nil, {}, {}, {}
    errors, warnings = {}, {}
    assetFailures = {}
    return Runtime.status()
end

function Runtime.apply(data, opts)
    local normalized, decodedTracks, duration = validate(data)
    opts = opts or {}
    local preview = opts.preview ~= false
    local target = opts.parent or Workspace
    if typeof(target) ~= "Instance" then fail("options.parent doit être une Instance") end
    if preview and target ~= Workspace then fail("la prévisualisation doit être dans Workspace") end
    local name = preview and PREVIEW_NAME or (opts.rootName or data.name or "DatakyFX")
    if type(name) ~= "string" or name == "" then fail("nom de conteneur invalide") end
    local previous = target:FindFirstChild(name)
    if previous and previous ~= root and previous:GetAttribute(OWNED) ~= true then fail("le conteneur " .. name .. " existe et n'appartient pas à Dataky FX") end
    local newOrigin = opts.origin and vector(opts.origin, 3, "options.origin") or (preview and Vector3.new(0, 10000, 0) or Vector3.zero)
    -- Validate camera before replacing the last good effect.
    if preview and opts.camera ~= false then
        local c = data.camera or {}
        local p = vector(c.position or {10,6,12}, 3, "camera.position")
        local t = vector(c.target or {0,1,0}, 3, "camera.target")
        if (p-t).Magnitude < 0.001 then fail("camera.position et target doivent différer") end
        local fov = finite(c.fov or 50, "camera.fov")
        if fov < 1 or fov > 120 then fail("camera.fov doit être entre 1 et 120") end
        if not Workspace.CurrentCamera then fail("CurrentCamera introuvable") end
    end
    generation += 1
    local ticket = generation
    local staging = Instance.new("Folder")
    staging.Name = name
    staging:SetAttribute(OWNED, true)
    staging:SetAttribute("DatakyFXProject", tostring(data.id or data.name or ""))
    staging:SetAttribute("DatakyFXPreview", preview)
    local built, builtSpecs = {}, {}
    local ok, message = pcall(function()
        for _, node in ipairs(normalized) do
            local object
            if node.class == "MeshPart" then
                if not node.properties.MeshId or node.properties.MeshId == "" then fail(node.id .. ".MeshId est requis pour un MeshPart") end
                local fidelity = {}
                if node.properties.RenderFidelity then fidelity.RenderFidelity = node.properties.RenderFidelity end
                local meshOk, result = pcall(function() return AssetService:CreateMeshPartAsync(Content.fromUri(node.properties.MeshId), fidelity) end)
                if not meshOk or not result then fail(node.id .. ".MeshId : chargement natif impossible : " .. tostring(result)) end
                object = result
            else
                object = Instance.new(node.class)
            end
            object.Name = node.name
            object:SetAttribute("DatakyFXNodeId", node.id)
            -- Keep every partially built instance beneath staging for failure cleanup.
            object.Parent = staging
            built[node.id], builtSpecs[node.id] = object, node
            if isBaseClass(node.class) then
                object.Anchored, object.CanCollide, object.CanTouch, object.CanQuery = true, false, false, false
                object.Position = newOrigin
            end
            for _, property in ipairs(orderedProperties(node.properties)) do
                local value = node.properties[property]
                if schema[node.class][property] ~= "reference" and property ~= "MeshId" and property ~= "Enabled" and property ~= "Position" and not (node.class == "MeshPart" and property == "RenderFidelity") then
                    -- MeshId is writable only on SpecialMesh; MeshPart uses CreateMeshPartAsync.
                    setProperty(object, property, value, node.id)
                end
            end
            if node.class == "SpecialMesh" and node.properties.MeshId then setProperty(object, "MeshId", node.properties.MeshId, node.id) end
            if node.properties.Position then
                setProperty(object, "Position", node.properties.Position + (isBaseClass(node.class) and newOrigin or Vector3.zero), node.id)
            end
            if isSwitchClass(node.class) then object.Enabled = false end
            if ticket ~= generation then fail("construction annulée") end
        end
        for _, node in ipairs(normalized) do
            built[node.id].Parent = node.parent and built[node.parent] or staging
            for property, value in pairs(node.properties) do
                if schema[node.class][property] == "reference" then setProperty(built[node.id], property, built[value], node.id) end
            end
        end
    end)
    if not ok then staging:Destroy(); fail(tostring(message)) end
    if ticket ~= generation then staging:Destroy(); fail("construction annulée") end
    Runtime.stop()
    if root and root:GetAttribute(OWNED) == true then root:Destroy() end
    if previous and previous ~= root and previous:GetAttribute(OWNED) == true then previous:Destroy() end
    root, project, objects, specs, tracks = staging, data, built, builtSpecs, decodedTracks
    options, origin, activeOptions = opts, newOrigin, opts
    options.duration = duration
    errors, warnings, fired, elapsed = {}, {}, {}, 0
    for id, spec in pairs(specs) do
        if (spec.class == "Beam" or spec.class == "Trail") and (not spec.properties.Attachment0 or not spec.properties.Attachment1) then
            table.insert(warnings, id .. " : reliez Attachment0 et Attachment1 pour afficher cet objet")
        end
    end
    root.Parent = target
    configureCamera(data, opts)
    monitorAssets()
    return Runtime.status()
end

-- Pilote des objets déjà présents (modèle .rbxmx glissé dans Studio) au lieu d'en construire :
-- chaque node est retrouvé sous target par son attribut DatakyFXNodeId. Le modèle n'est jamais détruit.
function Runtime.adopt(data, target, opts)
    local normalized, decodedTracks, duration = validate(data)
    opts = opts or {}
    if typeof(target) ~= "Instance" then fail("adopt exige l'Instance qui contient l'effet") end
    local byId, found, foundSpecs = {}, {}, {}
    for _, node in ipairs(normalized) do byId[node.id] = node end
    for _, object in ipairs(target:GetDescendants()) do
        local id = object:GetAttribute("DatakyFXNodeId")
        if type(id) == "string" and byId[id] and not found[id] and object.ClassName == byId[id].class then
            found[id], foundSpecs[id] = object, byId[id]
        end
    end
    for _, node in ipairs(normalized) do
        if not found[node.id] then fail(node.id .. " (" .. tostring(node.name) .. ") introuvable sous " .. target:GetFullName()) end
    end
    generation += 1
    cancelAssetMonitor()
    Runtime.stop()
    restoreCamera()
    if root and root ~= target and root:GetAttribute(OWNED) == true then root:Destroy() end
    root, project, objects, specs, tracks = target, data, found, foundSpecs, decodedTracks
    options, activeOptions = opts, opts
    origin = opts.origin and vector(opts.origin, 3, "options.origin") or Vector3.zero
    options.duration = duration
    errors, warnings, fired, elapsed, assetFailures = {}, {}, {}, 0, {}
    for id, spec in pairs(specs) do
        if isSwitchClass(spec.class) then objects[id].Enabled = false end
    end
    return Runtime.status()
end

local function lerp(a, b, alpha)
    local kind = typeof(a)
    if kind == "number" then return a + (b-a)*alpha end
    if kind == "Vector3" or kind == "Vector2" or kind == "Color3" then return a:Lerp(b, alpha) end
    if kind == "NumberRange" then return NumberRange.new(a.Min+(b.Min-a.Min)*alpha, a.Max+(b.Max-a.Max)*alpha) end
    return alpha >= 1 and b or a
end

local function sample(track, time)
    local keys = track.keyframes
    if time <= keys[1].time then return keys[1].value end
    for i = 2, #keys do
        if time < keys[i].time then
            local a, b = keys[i-1], keys[i]
            return lerp(a.value, b.value, (time-a.time)/(b.time-a.time))
        end
    end
    return keys[#keys].value
end

local function update(time)
    local animatedEnabled = {}
    for _, track in ipairs(tracks) do
        local value = sample(track, time)
        if track.property == "Position" and isBaseClass(specs[track.node].class) then value += origin end
        if track.property == "Enabled" then animatedEnabled[track.node] = value
        else setProperty(objects[track.node], track.property, value, track.node) end
    end
    for id, spec in pairs(specs) do
        local object = objects[id]
        local timing = spec.timing
        if timing then
            if timing.mode == "burst" then
                object.Enabled = false
                if time >= timing.start and not fired[id] then object:Emit(timing.count); fired[id] = true end
            else
                object.Enabled = spec.properties.Enabled ~= false and animatedEnabled[id] ~= false and time >= timing.start and time < timing.start + timing.duration
            end
        elseif isSwitchClass(spec.class) then
            object.Enabled = animatedEnabled[id] ~= nil and animatedEnabled[id] or (animatedEnabled[id] == nil and spec.properties.Enabled ~= false)
        end
    end
end

function Runtime.play(data, opts)
    if data then Runtime.apply(data, opts or activeOptions) end
    if not root or not root.Parent or not project then fail("aucun effet à lire") end
    Runtime.stop()
    running, paused, elapsed, fired = true, false, 0, {}
    local ok, message = pcall(update, 0)
    if not ok then Runtime.stop(); table.insert(errors, tostring(message)); fail(tostring(message)) end
    connection = RunService.Heartbeat:Connect(function(dt)
        if not running or paused then return end
        local stepOk, stepError = pcall(function()
            elapsed += dt
            if elapsed >= options.duration then
                update(options.duration)
                if project.loop then
                    clearVisuals(true)
                    elapsed, fired = elapsed % options.duration, {}
                    update(elapsed)
                else
                    running = false
                    disconnect()
                    clearVisuals(false)
                    elapsed = options.duration
                end
            else
                update(elapsed)
            end
        end)
        if not stepOk then
            table.insert(errors, tostring(stepError))
            Runtime.stop()
            warn("Dataky FX lecture interrompue : " .. tostring(stepError))
        end
    end)
    return Runtime.status()
end

-- ParticleEmitter.TimeScale can freeze native particles. Trail history has no
-- native time scale; refuse pause when an enabled Trail has a live history.
function Runtime.pause()
    if not running or paused then return Runtime.status() end
    for id, object in pairs(objects) do
        if specs[id].class == "Trail" then fail("pause indisponible pour un effet contenant une Trail ; Roblox ne permet pas de figer son historique") end
    end
    pausedProperties = {}
    for id, object in pairs(objects) do
        if specs[id].class == "ParticleEmitter" then
            pausedProperties[id] = {TimeScale=object.TimeScale, Enabled=object.Enabled}
            object.TimeScale, object.Enabled = 0, false
        elseif specs[id].class == "Beam" then
            pausedProperties[id] = {TextureSpeed=object.TextureSpeed}
            object.TextureSpeed = 0
        end
    end
    paused = true
    return Runtime.status()
end

function Runtime.resume()
    if not running or not paused then return Runtime.status() end
    for id, props in pairs(pausedProperties) do
        for property, value in pairs(props) do objects[id][property] = value end
    end
    pausedProperties, paused = {}, false
    return Runtime.status()
end

function Runtime.status()
    local count = 0
    for _ in pairs(objects) do count += 1 end
    return {
        version=1, name="Dataky FX Studio", project_id=project and project.id or nil,
        ready=root ~= nil and root.Parent ~= nil, playing=running, paused=paused, time=elapsed,
        duration=project and (project.duration or 3) or 0, node_count=count,
        root=root and root:GetFullName() or nil, errors=table.clone(errors), warnings=table.clone(warnings),
        loading_assets=loadingAssets, asset_failures=table.clone(assetFailures),
        native=true, camera_controlled=savedCamera ~= nil,
    }
end

Runtime.schema = schema
return Runtime
