-- Dataky FX Studio local bridge. Command bar auto-connects; the persistent
-- plugin starts disconnected and exposes a toolbar button in the chosen Studio.
local HttpService = game:GetService("HttpService")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")
local BASE = "http://127.0.0.1:48754"
local VERSION = 2
local isPlugin = plugin ~= nil
local CAPABILITIES = {native_preview=true, sandbox=true, commands={"export_used_textures"}, capture_context=isPlugin and "plugin" or "command_bar", capture_permission_request=isPlugin}
local old = _G.DatakyFXBridge
if old then
    if type(old.shutdown) == "function" then old.shutdown()
    elseif type(old.disconnect) == "function" then old.disconnect() end
end
local session = {alive=true, enabled=false, connected=false, last_error=nil, client_id=HttpService:GenerateGUID(false)}
session.capture_generation = 0
session.preview_enabled, session.preview_permission, session.preview_available = false, false, false
session.preview_error, session.preview_fps = nil, 4
local captureService, encodingService
local captureAvailable = pcall(function()
    captureService = game:GetService("StudioCaptureService")
    encodingService = game:GetService("EncodingService")
    assert(captureService and encodingService and Enum.StudioCaptureScreenshotFormat.PNG and Enum.UICaptureMode.None)
end)
session.preview_available = captureAvailable
local previewState, previewGeneration, permissionRequested = nil, 0, false
local runtime
if script then
    local module = script:FindFirstChild("Runtime") or (script.Parent and script.Parent:FindFirstChild("Runtime"))
    if module and module:IsA("ModuleScript") then runtime = require(module) end
end
if not runtime then
    assert(not isPlugin, "Dataky FX : le plugin doit contenir un ModuleScript Runtime (réinstallez DatakyFXStudio.rbxmx).")
    local source = HttpService:GetAsync(BASE .. "/bridge/runtime.lua", true)
    local fn, compileError = loadstring(source, "DatakyFXRuntime")
    assert(fn, "Dataky FX runtime : " .. tostring(compileError))
    runtime = fn()
end
assert(type(runtime) == "table" and type(runtime.apply) == "function", "Dataky FX : runtime invalide")
session.runtime = runtime

-- Keep the image relay and command polling under a shared HTTP budget.
-- Control requests take priority over frames. A small token bucket also avoids
-- exhausting the minute budget in a burst when a higher FPS is requested.
local requestTimes, httpTokens, httpUpdated = {}, 6, os.clock()
local function refreshHttpBudget()
    local now = os.clock()
    httpTokens = math.min(6, httpTokens+(now-httpUpdated)*6.8)
    httpUpdated = now
    while requestTimes[1] and requestTimes[1] <= now-60 do table.remove(requestTimes, 1) end
    return now
end

local function frameBudgetAvailable()
    refreshHttpBudget()
    return #requestTimes < 400 and httpTokens >= 2
end

local function request(method, path, payload)
    local frame = path == "/bridge/frame"
    local now = refreshHttpBudget()
    if frame and (#requestTimes >= 400 or httpTokens < 2) then return {skipped=true} end
    while #requestTimes >= 420 or httpTokens < 1 do
        task.wait(0.025)
        now = refreshHttpBudget()
    end
    httpTokens -= 1
    table.insert(requestTimes, now)
    local args = {Url=BASE .. path, Method=method, Headers={}}
    if payload then args.Body=HttpService:JSONEncode(payload); args.Headers["Content-Type"]="application/json" end
    local response = HttpService:RequestAsync(args)
    if not response.Success then error("HTTP " .. response.StatusCode .. " " .. response.Body, 0) end
    if response.Body == "" then return {} end
    return HttpService:JSONDecode(response.Body)
end

local function goodbye(clientId)
    -- RequestAsync has no public per-request timeout. Run the best-effort
    -- release separately so a stopped server never delays local cleanup.
    task.spawn(function()
        pcall(request, "POST", "/bridge/goodbye", {client_id=clientId})
    end)
end

local function captureStatus()
    return {
        enabled=session.preview_enabled, available=session.preview_available,
        permission=session.preview_permission, error=session.preview_error, fps=session.preview_fps,
        generation=session.capture_generation, adaptive=true, http_budget=420,
        window_focused=session.window_focused,
    }
end

local function sendPreviewStatus()
    local data = captureStatus()
    data.client_id = session.client_id
    -- Serialize status posts so an older "permission=false" or "enabled=true"
    -- response cannot arrive after a newer grant/stop and revive stale state.
    session.preview_status_pending = data
    if session.preview_status_sending then return end
    session.preview_status_sending = true
    task.spawn(function()
        while session.preview_status_pending do
            local pending = session.preview_status_pending
            session.preview_status_pending = nil
            pcall(request, "POST", "/bridge/preview_status", pending)
        end
        session.preview_status_sending = false
    end)
end

local function destroyCapture(state)
    if state and state.capture then
        pcall(function() state.capture:Destroy() end)
        state.capture = nil
    end
end

function session.previewStop(message)
    previewGeneration += 1
    session.preview_enabled = false
    session.preview_error = message
    local state = previewState
    previewState = nil
    if state then
        destroyCapture(state)
        if state.worker and state.worker ~= coroutine.running() then pcall(task.cancel, state.worker) end
    end
    if session.preview_button then session.preview_button:SetActive(false) end
    sendPreviewStatus()
    return captureStatus()
end

local function previewGate()
    if not session.alive or not session.enabled or not session.connected or RunService:IsRunning() then return nil end
    if session.preview_suspended then return nil end
    local status = runtime.status()
    local owned = Workspace:FindFirstChild("__DatakyFXPreview")
    if not status.ready or not status.camera_controlled or not owned then return nil end
    if owned:GetAttribute("DatakyFXOwned") ~= true or owned:GetAttribute("DatakyFXPreview") ~= true then return nil end
    local camera = Workspace.CurrentCamera
    if not camera or camera.CameraType ~= Enum.CameraType.Scriptable then return nil end
    return {root=owned, camera=camera, runtime=status, generation=session.capture_generation}
end

function session.previewStart(command)
    if session.preview_enabled then return captureStatus() end
    if not session.alive or not session.enabled or not session.connected then
        session.preview_error = "Connectez cette fenêtre Studio avant de démarrer l'aperçu."
        sendPreviewStatus()
        return captureStatus()
    end
    if not captureAvailable then
        session.preview_available = false
        session.preview_error = "StudioCaptureService est indisponible dans cette version de Roblox Studio."
        sendPreviewStatus()
        return captureStatus()
    end
    local fps = command and command.fps or 4
    if type(fps) ~= "number" or fps ~= fps then fps = 4 end
    session.preview_fps = math.clamp(fps, 1, 15)
    session.preview_enabled, session.preview_error = true, nil
    previewGeneration += 1
    local state = {ticket=previewGeneration, client_id=session.client_id}
    previewState = state
    if session.preview_button then session.preview_button:SetActive(true) end
    local function current()
        return previewState == state and state.ticket == previewGeneration and session.preview_enabled
            and session.alive and session.enabled and session.client_id == state.client_id
    end
    local function stopWithError(message)
        if current() then session.previewStop(message) end
    end
    sendPreviewStatus()
    state.worker = task.spawn(function()
        local permissionOk, permissionError = pcall(function()
            if not captureService:CanCaptureScreenshot() then
                if not isPlugin then
                    error("L'aperçu dans le site nécessite le plugin Dataky FX Studio installé et son autorisation de capture ; la connexion par commande bar reste utilisable pour éditer les effets.", 0)
                end
                if permissionRequested then
                    error("Autorisation de capture absente. Autorisez Dataky FX Studio dans les réglages de Studio, puis relancez le plugin.", 0)
                end
                permissionRequested = true
                session.preview_permission = captureService:RequestScreenshotPermissionAsync() == true
                if not current() then return end
                if not session.preview_permission then
                    error("Autorisation refusée ou capture indisponible. Autorisez les captures pour Dataky FX Studio dans les réglages de Studio.", 0)
                end
            end
            session.preview_permission, session.preview_available = true, true
        end)
        if not current() then return end
        if not permissionOk then stopWithError(tostring(permissionError)); return end
        sendPreviewStatus()
        while current() do
            local started = os.clock()
            local gate = previewGate()
            local retryDelay
            if gate and frameBudgetAvailable() then
                local ok, message = pcall(function()
                    if not captureService:CanCaptureScreenshot() then
                        local warning = "Aperçu en pause : activez la fenêtre Roblox Studio pour reprendre les captures."
                        if session.preview_error ~= warning then session.preview_error = warning; sendPreviewStatus() end
                        retryDelay = 2
                        return
                    end
                    if session.preview_error then session.preview_error = nil; sendPreviewStatus() end
                    local size = gate.camera.ViewportSize
                    if size.X < 1 or size.Y < 1 then error("Le viewport Studio n'est pas visible.", 0) end
                    local scale = math.min(1, 1280/size.X, 720/size.Y)
                    local output = Vector2.new(math.max(1, math.floor(size.X*scale)), math.max(1, math.floor(size.Y*scale)))
                    local capture = captureService:CaptureScreenshot({
                        Position=Vector2.zero, CaptureSize=size, OutputSize=output,
                        ResampleMode=Enum.ResamplerMode.Default, Format=Enum.StudioCaptureScreenshotFormat.PNG,
                        UICaptureMode=Enum.UICaptureMode.None,
                    })
                    state.capture = capture
                    local deadline = os.clock()+10
                    while current() and capture.BufferStatus ~= Enum.StudioCaptureBufferStatus.Ready do
                        if capture.BufferStatus == Enum.StudioCaptureBufferStatus.Error then
                            local details = capture:GetErrors()
                            error("Capture Studio : " .. table.concat(details, "; "), 0)
                        end
                        if os.clock() >= deadline then error("La capture Studio n'a pas répondu après 10 secondes.", 0) end
                        task.wait(0.025)
                    end
                    if not current() then destroyCapture(state); return end
                    local after = previewGate()
                    if not after or after.root ~= gate.root or after.camera ~= gate.camera or after.generation ~= gate.generation then
                        destroyCapture(state)
                        return
                    end
                    if capture.BufferFormat ~= Enum.StudioCaptureScreenshotFormat.PNG then error("Studio a renvoyé un format de capture différent du PNG demandé.", 0) end
                    local bytes = capture:GetBuffer()
                    local image = "data:image/png;base64," .. buffer.tostring(encodingService:Base64Encode(bytes))
                    destroyCapture(state)
                    if not current() or session.capture_generation ~= gate.generation then return end
                    request("POST", "/bridge/frame", {
                        client_id=state.client_id, image=image, generation=gate.generation,
                        time=gate.runtime.time, project_id=gate.runtime.project_id, runtime=gate.runtime,
                    })
                end)
                destroyCapture(state)
                if not current() then return end
                if not ok and not tostring(message):match("^HTTP 409 ") then stopWithError(tostring(message)); return end
            end
            task.wait(retryDelay or math.max(0.01, 1/session.preview_fps-(os.clock()-started)))
        end
    end)
    return captureStatus()
end

function session.status()
    return {
        client_id=session.client_id,connected=session.connected,enabled=session.enabled,
        alive=session.alive,last_error=session.last_error,runtime=runtime.status(),version=VERSION,capabilities=CAPABILITIES,
        capture=captureStatus(),
    }
end

function session.connect()
    if not session.alive then return session.status() end
    if not session.enabled then
        session.client_id = HttpService:GenerateGUID(false)
        session.enabled, session.connected, session.last_error = true, false, nil
        if session.button then session.button:SetActive(true) end
    end
    return session.status()
end

function session.disconnect()
    if not session.alive then return session.status() end
    local clientId = session.client_id
    session.previewStop()
    session.enabled, session.connected = false, false
    runtime.clear()
    if session.button then session.button:SetActive(false) end
    goodbye(clientId)
    return session.status()
end

-- BEGIN USED TEXTURE SCAN: literal recipe data is read, never required/executed.
local function collectUsedTextures(place)
    local ids, unreadable, dynamic = {}, 0, 0
    local function add(value)
        if type(value) ~= "string" then value = tostring(value or "") end
        local id = value:match("^rbxassetid://(%d+)$") or value:match("^%d+$")
        if not id then id = value:match("^https?://www%.roblox%.com/asset/?%?id=(%d+)$") or value:match("^https?://roblox%.com/asset/?%?id=(%d+)$") end
        if id then
            id = id:gsub("^0+", "")
            if id ~= "" then ids[id] = true end
        end
    end
    for _, object in ipairs(place:GetDescendants()) do
        if object:IsA("ParticleEmitter") or object:IsA("Beam") or object:IsA("Trail") then
            add(object.Texture)
        elseif object:IsA("ModuleScript") then
            local ok, source = pcall(function() return object.Source end)
            if not ok then unreadable += 1
            elseif source:find("nodes") and source:find("version") then
                -- Exported libraries and ordinary literal recipe tables (Lua/JSON).
                -- Dynamic expressions are not evaluated; report them for inspection.
                for _, field in ipairs({"Texture", "TextureID", "TextureId"}) do
                    local prefix = "%f[%w_]" .. field .. "%f[^%w_][\"'%]%s]*[=:]%s*"
                    for expression in source:gmatch(prefix .. "([^,;\n}]+)") do
                        expression = expression:gsub("%s+$", "")
                        local literal = expression:match('^"([^"]*)"$') or expression:match("^'([^']*)'$") or expression:match("^%d+$")
                        if literal then add(literal) else dynamic += 1 end
                    end
                end
            end
        end
    end
    local result = {}
    for id in pairs(ids) do table.insert(result, id) end
    table.sort(result, function(a, b) return #a == #b and a < b or #a < #b end)
    return result, unreadable, dynamic
end
-- END USED TEXTURE SCAN

function session.exportUsedTextures()
    assert(RunService:IsEdit() and not RunService:IsRunning(), "Exporter les textures utilisées exige le mode édition.")
    assert(session.connected, "Cliquez sur Connexion et attendez la connexion à Dataky FX Studio.")
    local ids, unreadable, dynamic = collectUsedTextures(game)
    local result = request("POST", "/bridge/used_textures", {client_id=session.client_id, place_name=game.Name, ids=ids})
    result.unreadable_modules, result.dynamic_expressions = unreadable, dynamic
    print("Dataky FX Studio : " .. tostring(result.count) .. " textures exportées dans " .. tostring(result.path))
    if unreadable > 0 or dynamic > 0 then
        warn("Dataky FX Studio : scan partiel, " .. unreadable .. " modules illisibles et " .. dynamic .. " expressions dynamiques à vérifier.")
    end
    return result
end

function session.shutdown()
    if not session.alive then return end
    session.disconnect()
    session.alive = false
    if session.click_connection then session.click_connection:Disconnect() end
    if session.unloading_connection then session.unloading_connection:Disconnect() end
    if session.button then session.button:Destroy() end
    if session.preview_click_connection then session.preview_click_connection:Disconnect() end
    if session.preview_button then session.preview_button:Destroy() end
    if session.textures_click_connection then session.textures_click_connection:Disconnect() end
    if session.textures_button then session.textures_button:Destroy() end
    if session.toolbar then session.toolbar:Destroy() end
    if session.focus_connection then session.focus_connection:Disconnect() end
    if session.blur_connection then session.blur_connection:Disconnect() end
end

-- These documented signals concern the main Roblox viewport. No initial focus
-- is assumed, and their delivery in a Studio plugin still needs a live check.
pcall(function()
    local input = game:GetService("UserInputService")
    session.focus_connection = input.WindowFocused:Connect(function()
        session.window_focused = true
        if session.enabled then sendPreviewStatus() end
    end)
    session.blur_connection = input.WindowFocusReleased:Connect(function()
        session.window_focused = false
        if session.enabled then sendPreviewStatus() end
    end)
end)

if isPlugin then
    session.toolbar = plugin:CreateToolbar("Dataky FX")
    session.button = session.toolbar:CreateButton("DatakyFXConnection", "Connecter ou déconnecter Dataky FX Studio dans cette fenêtre", "", "Connexion")
    session.button.ClickableWhenViewportHidden = true
    session.button:SetActive(false)
    session.click_connection = session.button.Click:Connect(function()
        if session.enabled then session.disconnect() else session.connect() end
    end)
    session.preview_button = session.toolbar:CreateButton("DatakyFXPreview", "Afficher le viewport Roblox dans Dataky FX Studio", "", "Aperçu")
    session.preview_button.ClickableWhenViewportHidden = true
    session.preview_button:SetActive(false)
    session.preview_click_connection = session.preview_button.Click:Connect(function()
        if session.preview_enabled then session.previewStop() else session.previewStart() end
    end)
    session.textures_button = session.toolbar:CreateButton("DatakyFXUsedTextures", "Exporter les textures utilisées dans tool/used_textures", "", "Exporter les textures utilisées")
    session.textures_button.ClickableWhenViewportHidden = true
    session.textures_click_connection = session.textures_button.Click:Connect(function()
        task.spawn(function()
            local ok, message = pcall(session.exportUsedTextures)
            if not ok then session.last_error = tostring(message); warn("Dataky FX Studio : " .. tostring(message)) end
        end)
    end)
    session.unloading_connection = plugin.Unloading:Connect(session.shutdown)
end
_G.DatakyFXBridge = session

local actions = {
    apply=function(command) return runtime.apply(command.project) end,
    play=function(command) return runtime.play(command.project) end,
    stop=function() session.previewStop(); return runtime.stop() end,
    clear=function() session.previewStop(); return runtime.clear() end,
    status=function() return runtime.status() end,
    pause=function() return runtime.pause() end,
    resume=function() return runtime.resume() end,
    sandbox=function(command)
        if command.mode == "timeline" then return runtime.play(command.project) end
        return runtime.sandbox(command.project, command.enabled)
    end,
    emit=function(command) return runtime.emit(command.counts) end,
    enabled=function(command) return runtime.enabled(command.enabled) end,
    clear_particles=function() return runtime.clearParticles() end,
    update=function(command) return runtime.update(command.project) end,
    preview_start=function(command) return session.previewStart(command) end,
    preview_stop=function() return session.previewStop() end,
    capture_status=function() return captureStatus() end,
    export_used_textures=function() return session.exportUsedTextures() end,
}

if not isPlugin then session.connect() end

task.spawn(function()
    local lastHello, seen, seenOrder, lastClient = -math.huge, {}, {}, nil
    local transportFailure = nil
    while session.alive do
        if not session.enabled then task.wait(0.2); continue end
        if RunService:IsRunning() then
            session.disconnect()
            session.last_error = "Quittez le mode Play, puis reconnectez Dataky FX Studio en mode édition."
            task.wait(0.2)
            continue
        end
        local clientId = session.client_id
        if clientId ~= lastClient then
            lastHello, seen, seenOrder, transportFailure, lastClient = -math.huge, {}, {}, nil, clientId
        end
        local function stillCurrent()
            return session.alive and session.enabled and session.client_id == clientId
        end
        local ok, message = pcall(function()
            if os.clock()-lastHello >= 5 then
                request("POST", "/bridge/hello", {
                    client_id=clientId, studio=game.Name, place_id=game.PlaceId, version=VERSION,capabilities=CAPABILITIES,
                    details=runtime.status(),
                    capture=captureStatus(),
                })
                if not stillCurrent() then return end
                lastHello = os.clock()
            end
            local response = request("GET", "/bridge/poll?client_id=" .. HttpService:UrlEncode(clientId))
            if not stillCurrent() then return end
            session.connected, session.last_error, transportFailure = true, nil, nil
            local command = response.command
            if command then
                assert(type(command.id) == "string" or type(command.id) == "number", "Commande sans ID")
                local ack = seen[command.id]
                if not ack then
                    if type(command.capture_generation) == "number" then session.capture_generation = math.max(session.capture_generation, command.capture_generation) end
                    session.preview_suspended = command.action == "apply" or command.action == "play"
                    local action = actions[command.action]
                    local actionOk, details = pcall(function()
                        assert(action, "Action interdite " .. tostring(command.action))
                        if not stillCurrent() then error("Session fermée") end
                        return action(command)
                    end)
                    session.preview_suspended = false
                    -- Asset creation may yield; disconnected work cannot leave
                    -- a preview or acknowledge a later client lease.
                    if not stillCurrent() then runtime.clear(); return end
                    ack = {client_id=clientId,id=command.id,ok=actionOk}
                    if actionOk then ack.details=details else ack.error=tostring(details); session.last_error=tostring(details) end
                    seen[command.id] = ack
                    table.insert(seenOrder, command.id)
                    if #seenOrder > 128 then seen[table.remove(seenOrder,1)] = nil end
                end
                request("POST", "/bridge/ack", ack)
            end
        end)
        if not ok and stillCurrent() then
            session.last_error, session.connected = tostring(message), false
            lastHello = -math.huge
            transportFailure = transportFailure or os.clock()
            if os.clock()-transportFailure > 20 then session.previewStop(); runtime.clear() end
        end
        task.wait(ok and (session.preview_enabled and 0.5 or 0.2) or 1)
    end
end)

-- Studio loads plugins in the Play client and server too. Keep this Edit hint
-- once per session, including when the bridge script is reloaded.
if RunService:IsEdit() and not RunService:IsRunning() and not _G.DatakyFXConnectionHintShown then
    _G.DatakyFXConnectionHintShown = true
    print(isPlugin and "Dataky FX Studio : cliquez sur Connexion dans la barre Dataky FX." or "Dataky FX Studio : pont local démarré sur " .. BASE)
end
return session.status()
