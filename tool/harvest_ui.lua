-- Read-only texture catalogue capture for ZonitoVisuals v4.1.
-- Only scrolls the plugin UI. Does not insert, remove, or change place instances.
-- Run with the local receive.py sink, then _G.ZonitoCapture("Circle") etc.
local Http = game:GetService("HttpService")
local main
for _, gui in ipairs(game:GetService("PluginGuiService"):GetChildren()) do
    local candidate = gui:FindFirstChild("Main")
    local title = candidate and candidate:FindFirstChild("Topbar") and candidate.Topbar:FindFirstChild("Title")
    if candidate and candidate:FindFirstChild("Textures") and title and title:IsA("TextLabel") and title.Text == "ZonitoVisuals" then
        main = candidate
        break
    end
end
assert(main, "Open ZonitoVisuals texture tab first")

_G.ZonitoCaptureState = {status = "ready"}
_G.ZonitoCapture = function(label)
    assert(_G.ZonitoCaptureState.status ~= "running", "Capture already running")
    local frame = main.Textures
    local filter = main.Topbar.ScalingBar.TagDropdown.Background.Tip.Text:gsub("<[^>]+>", ""):lower()
    local typeCapture = label == "Statics" or label == "Flipbooks"
    local expected = (label == "All" or typeCapture) and "tags" or label:lower()
    assert(filter == expected, "Unexpected active tags: " .. filter .. " (expected " .. expected .. ")")
    local activeType
    for _, button in ipairs(main.Topbar.ScalingBar.TextureType:GetChildren()) do
        if button:IsA("TextButton") and button.TextTransparency < 0.3 then
            assert(not activeType, "Multiple active texture types")
            activeType = button.Name
        end
    end
    assert(activeType == (typeCapture and label or "All"), "Unexpected active texture type: " .. tostring(activeType))
    _G.ZonitoCaptureCancelled = false
    local original = frame.CanvasPosition
    local state = {status = "running", label = label, count = 0, position = 0}
    _G.ZonitoCaptureState = state
    task.spawn(function()
        local ok, message = xpcall(function()
            local byIndex = {}
            local function collect()
                for _, button in ipairs(frame:GetChildren()) do
                    if button:IsA("ImageButton") and button.Visible then
                        local index = button:GetAttribute("Index")
                        local uri = button:GetAttribute("LastTexture")
                        local image = button:FindFirstChild("Texture")
                        if index and uri and string.sub(button.Name, 1, 2) ~= "__" then
                            byIndex[index] = {
                                index = index, name = button.Name, raw_uri = uri,
                                image = image and image.Image or uri,
                                rect_size = image and {image.ImageRectSize.X, image.ImageRectSize.Y} or {0,0},
                                rect_offset = image and {image.ImageRectOffset.X, image.ImageRectOffset.Y} or {0,0},
                            }
                        end
                    end
                end
                local count = 0
                for _ in pairs(byIndex) do count += 1 end
                state.count = count
                state.position = frame.CanvasPosition.Y
            end
            frame.CanvasPosition = Vector2.zero
            task.wait(0.35)
            local height = frame.AbsoluteCanvasSize.Y
            local window = frame.AbsoluteWindowSize.Y
            assert(window > 20, "Texture panel is too small")
            local finish = math.max(0, height - window)
            local step = math.max(40, math.floor(window * 0.65))
            for position = 0, finish + step, step do
                assert(not _G.ZonitoCaptureCancelled, "Capture cancelled")
                frame.CanvasPosition = Vector2.new(0, math.min(position, finish))
                task.wait(0.08)
                collect()
            end
            local records = {}
            local maxIndex = 2
            for index, record in pairs(byIndex) do
                table.insert(records, record)
                maxIndex = math.max(maxIndex, index)
            end
            table.sort(records, function(a,b) return a.index < b.index end)
            local missing = {}
            for index = 3, maxIndex do
                if not byIndex[index] then table.insert(missing, index) end
            end
            -- Every virtualized slot has a monotonically numbered Index.
            -- Gaps are recorded and never silently treated as a complete sweep.
            local payload = {
                label = label, records = records, max_index = maxIndex,
                missing_indexes = missing, canvas_height = height, window_height = window,
                search = main.Topbar.ScalingBar.SearchBar.Text,
                active_filter = filter,
                active_type = activeType,
                captured_at = DateTime.now():ToIsoDate(),
            }
            _G.ZonitoCaptureLastPayload = payload
            local parts = math.max(1, math.ceil(#records / 750))
            for part = 1, parts do
                local batch = table.clone(payload)
                batch.records = {}
                batch.part = part
                batch.total_parts = parts
                for n = (part - 1) * 750 + 1, math.min(part * 750, #records) do
                    table.insert(batch.records, records[n])
                end
                state.saved = Http:PostAsync(_G.ZonitoCaptureSink or "http://127.0.0.1:48753/capture", Http:JSONEncode(batch), Enum.HttpContentType.ApplicationJson)
                state.saved_parts = part
            end
            state.missing = #missing
            state.max_index = maxIndex
            state.status = "done"
        end, debug.traceback)
        frame.CanvasPosition = original
        if not ok then state.status = "error"; state.error = tostring(message) end
    end)
    return "started " .. label
end
return "ZonitoCapture ready"
