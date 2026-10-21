-- User-run macro bridge. Only plugin UI properties are changed.
local Http = game:GetService("HttpService")
local BASE = "http://127.0.0.1:48754"
local TOKEN = "__TOKEN__"
local COLLECTIONS = {textures = "Textures", beams = "Beams", meshes = "Meshes"}
local function endpoint(path) return BASE .. path .. "?token=" .. TOKEN end
local main
for _, gui in ipairs(game:GetService("PluginGuiService"):GetChildren()) do
    local candidate = gui:FindFirstChild("Main")
    local top = candidate and candidate:FindFirstChild("Topbar")
    local title = top and top:FindFirstChild("Title")
    if title and title:IsA("TextLabel") and title.Text == "ZonitoVisuals"
        and candidate:FindFirstChild("Textures") and candidate:FindFirstChild("Beams")
        and candidate:FindFirstChild("Meshes") then
        main = candidate
        break
    end
end
assert(main, "Open ZonitoVisuals first")
local scaling = main.Topbar.ScalingBar
local dropdown = scaling.TagDropdown.Dropdown
local original = {dropdownVisible = dropdown.Visible, dropdownPosition = dropdown.CanvasPosition, positions = {}}
for key, name in pairs(COLLECTIONS) do original.positions[key] = main[name].CanvasPosition end
_G.ZonitoCaptureSink = endpoint("/capture")
_G.ZonitoAssetCaptureSink = endpoint("/capture")
local stopped = false
local function center(item)
    local origin = main.AbsolutePosition
    local position, size = item.AbsolutePosition, item.AbsoluteSize
    return {x = position.X - origin.X + size.X / 2, y = position.Y - origin.Y + size.Y / 2}
end
local function selectedText() return scaling.TagDropdown.Background.Tip.Text:gsub("<[^>]+>", "") end
local function activeCollection()
    local selected
    for key, name in pairs(COLLECTIONS) do
        if main[name].Visible then
            assert(not selected, "Multiple visible collection panels")
            selected = key
        end
    end
    assert(selected, "Keep Textures, Beams or Meshes visible")
    return selected
end
local function activeType()
    if activeCollection() ~= "textures" then return nil end
    local selected
    for _, button in ipairs(scaling.TextureType:GetChildren()) do
        if button:IsA("TextButton") and button.TextTransparency < 0.3 then
            assert(not selected, "Multiple active texture types")
            selected = button.Name
        end
    end
    assert(selected, "No active texture type")
    return selected
end
local function layout(command)
    assert(main.Visible, "Keep the plugin visible")
    local collection = activeCollection()
    if command.collection then assert(command.collection == collection, "Unexpected active collection") end
    local tag = command.tag
    local button
    if tag and tag ~= "All" then
        button = dropdown:FindFirstChild(tag)
        assert(button and button:IsA("ImageButton"), "Unknown tag " .. tostring(tag))
        dropdown.Visible = true
        task.wait(0.08)
        local contentY = button.AbsolutePosition.Y - dropdown.AbsolutePosition.Y + dropdown.CanvasPosition.Y
        local maximum = math.max(0, dropdown.AbsoluteCanvasSize.Y - dropdown.AbsoluteWindowSize.Y)
        dropdown.CanvasPosition = Vector2.new(0, math.clamp(contentY - dropdown.AbsoluteWindowSize.Y / 2 + button.AbsoluteSize.Y / 2, 0, maximum))
        task.wait(0.08)
        local point = button.AbsolutePosition + button.AbsoluteSize / 2
        assert(point.Y >= dropdown.AbsolutePosition.Y and point.Y <= dropdown.AbsolutePosition.Y + dropdown.AbsoluteWindowSize.Y, "Tag is outside dropdown viewport")
    end
    local tags, typeButtons, typeLabels, sidebars = {}, {}, {}, {}
    for _, item in ipairs(dropdown:GetChildren()) do
        if item:IsA("ImageButton") then table.insert(tags, item.Name) end
    end
    table.sort(tags)
    for key, name in pairs(COLLECTIONS) do
        local control = main.Sidebar.List:FindFirstChild(name)
        assert(control and control:IsA("GuiButton"), "Missing sidebar button " .. name)
        sidebars[key] = center(control)
    end
    if collection == "textures" then
        for _, control in ipairs(scaling.TextureType:GetChildren()) do
            if control:IsA("TextButton") then
                typeButtons[control.Name], typeLabels[control.Name] = center(control), control.Text
            end
        end
    end
    local textureType = command.texture_type
    local typeButton = textureType and scaling.TextureType:FindFirstChild(textureType)
    assert(not textureType or (collection == "textures" and typeButton and typeButton:IsA("TextButton")), "Unknown texture type " .. tostring(textureType))
    assert(not command.target_collection or sidebars[command.target_collection], "Unknown target collection")
    return {
        header = center(scaling.TagDropdown), button = button and center(button) or nil,
        all_type = collection == "textures" and typeButtons.All or nil,
        type_button = typeButton and center(typeButton) or nil,
        type_buttons = typeButtons, type_labels = typeLabels, active_type = activeType(),
        collection_buttons = sidebars,
        collection_button = command.target_collection and sidebars[command.target_collection] or nil,
        active_collection = COLLECTIONS[collection], collection = collection,
        width = main.AbsoluteSize.X, height = main.AbsoluteSize.Y,
        main_origin = {x = main.AbsolutePosition.X, y = main.AbsolutePosition.Y},
        selected = selectedText(), search = scaling.SearchBar.Text, tags = tags,
    }
end
local function restore()
    _G.ZonitoCaptureCancelled, _G.ZonitoAssetCaptureCancelled = true, true
    dropdown.CanvasPosition, dropdown.Visible = original.dropdownPosition, original.dropdownVisible
    for key, name in pairs(COLLECTIONS) do main[name].CanvasPosition = original.positions[key] end
end
local function dispatch(command)
    if command.op == "layout" then return layout(command) end
    if command.op == "status" then
        local collection = activeCollection()
        if command.collection then assert(command.collection == collection, "Collection changed during capture") end
        return {capture = collection == "textures" and (_G.ZonitoCaptureState or {}) or (_G.ZonitoAssetCaptureState or {}),
            selected = selectedText(), search = scaling.SearchBar.Text, active_type = activeType(),
            active_collection = COLLECTIONS[collection], collection = collection}
    end
    if command.op == "capture" then
        local collection = activeCollection()
        assert(command.collection == collection, "Unexpected capture collection")
        assert(scaling.SearchBar.Text == "", "Search field must be empty")
        local typeCapture = collection == "textures" and (command.label == "Statics" or command.label == "Flipbooks")
        local expected = (command.label == "All" or typeCapture) and "Tags" or command.label
        assert(string.lower(selectedText()) == string.lower(expected), "Unexpected tag selection: " .. selectedText())
        if command.label == "All" then
            assert(type(command.expected_tags) == "table", "Missing expected tag manifest")
            if collection == "textures" then _G.ZonitoCaptureExpectedTags = command.expected_tags else
                _G.ZonitoAssetExpectedTags = _G.ZonitoAssetExpectedTags or {}
                _G.ZonitoAssetExpectedTags[collection] = command.expected_tags
            end
        end
        if collection == "textures" then
            assert(activeType() == (typeCapture and command.label or "All"), "Unexpected active texture type")
            assert(type(_G.ZonitoCapture) == "function", "Texture capture helper is missing")
            _G.ZonitoCaptureSink = endpoint("/capture")
            _G.ZonitoCapture(command.label)
        else
            assert(type(_G.ZonitoAssetCapture) == "function", "Asset capture helper is missing")
            _G.ZonitoAssetCaptureSink = endpoint("/capture")
            _G.ZonitoAssetCapture(collection, command.label)
        end
        return {started = command.label, collection = collection}
    end
    if command.op == "restore" then restore(); stopped = true; return {restored = true} end
    error("Unsupported bridge command")
end
local generation = {}
_G.ZonitoMacroGeneration, _G.ZonitoMacroBridgeState = generation, "ready"
task.spawn(function()
    local failures = 0
    while not stopped and _G.ZonitoMacroGeneration == generation do
        local ok, failure = pcall(function()
            local command = Http:JSONDecode(Http:GetAsync(endpoint("/next"), true))
            if command.op ~= "idle" then
                local success, result = xpcall(function() return dispatch(command) end, debug.traceback)
                Http:PostAsync(endpoint("/reply"), Http:JSONEncode({id = command.id, ok = success,
                    result = success and result or nil, error = not success and tostring(result) or nil}), Enum.HttpContentType.ApplicationJson)
            end
        end)
        if ok then failures = 0 else
            failures += 1
            if failures >= 10 then _G.ZonitoMacroBridgeState = tostring(failure); pcall(restore); break end
        end
        task.wait(0.12)
    end
    if stopped then _G.ZonitoMacroBridgeState = "stopped" end
end)
print("Zonito macro bridge ready. Hover the Tags header and press F8.")
return "Zonito macro bridge ready"
