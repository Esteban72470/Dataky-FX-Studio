-- Catalogue the Beams/Meshes UI without changing place instances.
local Http = game:GetService("HttpService")
local main
for _, gui in ipairs(game:GetService("PluginGuiService"):GetChildren()) do
    local candidate = gui:FindFirstChild("Main")
    local title = candidate and candidate:FindFirstChild("Topbar") and candidate.Topbar:FindFirstChild("Title")
    if title and title:IsA("TextLabel") and title.Text == "ZonitoVisuals" and candidate:FindFirstChild("Beams") and candidate:FindFirstChild("Meshes") then
        main = candidate
        break
    end
end
assert(main, "Open ZonitoVisuals first")
local frames = {beams = "Beams", meshes = "Meshes"}
local function filterText()
    return main.Topbar.ScalingBar.TagDropdown.Background.Tip.Text:gsub("<[^>]+>", ""):lower()
end
_G.ZonitoAssetCaptureState = {status = "ready"}
_G.ZonitoAssetCapture = function(collection, label)
    assert(frames[collection], "Unknown collection")
    assert(_G.ZonitoAssetCaptureState.status ~= "running", "Capture already running")
    local frame = main[frames[collection]]
    assert(frame.Visible, "Keep " .. frames[collection] .. " visible")
    assert(main.Topbar.ScalingBar.SearchBar.Text == "", "Clear the search first")
    local filter = filterText()
    local expected = label == "All" and "tags" or label:lower()
    assert(filter == expected, "Unexpected active tags: " .. filter .. " (expected " .. expected .. ")")
    local original = frame.CanvasPosition
    _G.ZonitoAssetCaptureCancelled = false
    local state = {status = "running", collection = collection, label = label, count = 0}
    _G.ZonitoAssetCaptureState = state
    task.spawn(function()
        local ok, err = xpcall(function()
            local byIndex = {}
            local function collect()
                assert(not _G.ZonitoAssetCaptureCancelled, "Capture cancelled")
                assert(frame.Visible and filterText() == filter and main.Topbar.ScalingBar.SearchBar.Text == "", "Collection or filters changed during capture")
                for _, button in ipairs(frame:GetChildren()) do
                    local index = button:GetAttribute("Index")
                    if button:IsA("GuiButton") and button.Visible and type(index) == "number" and index >= 3 and button.Name:sub(1,2) ~= "__" then
                        local refs = {}
                        local uri = button:GetAttribute("LastTexture") or ""
                        local img = button:FindFirstChild("Texture")
                        local meshUri, textureUri = "", ""
                        if collection == "meshes" then
                            for _, object in ipairs(button:GetDescendants()) do
                                if object:IsA("SpecialMesh") or object:IsA("MeshPart") then
                                    local mesh = object.MeshId
                                    local texture = object:IsA("SpecialMesh") and object.TextureId or object.TextureID
                                    if meshUri == "" then meshUri = mesh end
                                    if textureUri == "" then textureUri = texture end
                                    if mesh ~= "" then table.insert(refs, {label = "MeshId", raw_uri = mesh}) end
                                    if texture ~= "" then table.insert(refs, {label = "TextureId", raw_uri = texture}) end
                                end
                            end
                            uri = meshUri
                        end
                        byIndex[index] = {index = index, name = button.Name, raw_uri = uri,
                            image = img and img.Image or "", mesh_uri = meshUri, texture_uri = textureUri,
                            references = refs}
                    end
                end
                local count = 0
                for _ in pairs(byIndex) do count += 1 end
                state.count, state.position = count, frame.CanvasPosition.Y
            end
            frame.CanvasPosition = Vector2.zero
            task.wait(0.35)
            local height, window = frame.AbsoluteCanvasSize.Y, frame.AbsoluteWindowSize.Y
            assert(window > 20, "Asset panel is too small")
            local finish, step = math.max(0, height - window), math.max(40, math.floor(window * 0.65))
            for position = 0, finish + step, step do
                frame.CanvasPosition = Vector2.new(0, math.min(position, finish))
                task.wait(0.12)
                collect()
            end
            local records, maximum, missing = {}, 2, {}
            for index, row in pairs(byIndex) do table.insert(records, row); maximum = math.max(maximum, index) end
            table.sort(records, function(a,b) return a.index < b.index end)
            for index = 3, maximum do if not byIndex[index] then table.insert(missing, index) end end
            local tags = {}
            for _, button in ipairs(main.Topbar.ScalingBar.TagDropdown.Dropdown:GetChildren()) do
                if button:IsA("ImageButton") then table.insert(tags, button.Name) end
            end
            table.sort(tags)
            local payload = {collection = collection, active_collection = frames[collection], label = label,
                records = records, first_index = 3, max_index = maximum, missing_indexes = missing,
                canvas_height = height, window_height = window, search = "", active_filter = filter,
                available_tags = tags,
                expected_tags = _G.ZonitoAssetExpectedTags and _G.ZonitoAssetExpectedTags[collection] or nil,
                captured_at = DateTime.now():ToIsoDate()}
            _G.ZonitoAssetCaptureLastPayload = payload
            local parts = math.max(1, math.ceil(#records / 750))
            for part = 1, parts do
                local batch = table.clone(payload)
                batch.records, batch.part, batch.total_parts = {}, part, parts
                for n = (part - 1)*750 + 1, math.min(part*750, #records) do table.insert(batch.records, records[n]) end
                state.saved = Http:PostAsync(_G.ZonitoAssetCaptureSink or "http://127.0.0.1:48753/capture", Http:JSONEncode(batch), Enum.HttpContentType.ApplicationJson)
            end
            state.max_index, state.missing, state.status = maximum, #missing, "done"
        end, debug.traceback)
        frame.CanvasPosition = original
        if not ok then state.status, state.error = "error", tostring(err) end
    end)
    return "started " .. collection .. "/" .. label
end
return "ZonitoAssetCapture ready"
