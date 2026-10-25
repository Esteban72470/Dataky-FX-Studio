--!strict
-- Isolated, client-only presentation of the handwritten Enuma Elish effect.
-- The ModuleScript keeps the exact exported effect. This harness adds only the
-- camera, avatar visibility, optional impact grading and playback controls.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Lighting = game:GetService("Lighting")
local TweenService = game:GetService("TweenService")
local HttpService = game:GetService("HttpService")
local Workspace = game:GetService("Workspace")

type Status = { [string]: any }
type Effect = {
	build: (Instance, Vector3) -> Status,
	play: () -> Status,
	stop: () -> Status,
	pause: () -> Status,
	clear: () -> Status,
	status: () -> Status,
}

local player = Players.LocalPlayer
assert(player, "EnumaPreview must run on the client")
local module = ReplicatedStorage:WaitForChild("EnumaElish")
assert(module:IsA("ModuleScript"), "ReplicatedStorage.EnumaElish must be the exported ModuleScript")
local effect = require(module) :: Effect
local CAMERA_POSITION = Vector3.new(45, 27, 52)
local CAMERA_TARGET = Vector3.new(0, 15, 0)
local CAMERA_FOV = 48
local CAMERA_BINDING = "DatakyEnumaElishPreviewCamera"
local REPEAT_SECONDS = 31
local PULSE_TIMES = { 2.92, 10.22, 18.62 }
local impactPulses = script:GetAttribute("ImpactPulses") ~= false

local alive = true
local manualControl = false
local castVersion = 0
local automaticThread: thread? = nil
local connections: { RBXScriptConnection } = {}
local originalPartTransparency: { [BasePart]: number } = {}
local originalDecalTransparency: { [Decal]: number } = {}
local savedCamera = Workspace.CurrentCamera
local savedCameraType = if savedCamera then savedCamera.CameraType else nil
local savedCameraFrame = if savedCamera then savedCamera.CFrame else nil
local savedCameraFov = if savedCamera then savedCamera.FieldOfView else nil

local grade = Instance.new("ColorCorrectionEffect")
grade.Name = "EnumaPreviewImpact"
grade.Enabled = true
grade.Parent = Lighting
local gradeTween: Tween? = nil

local function resetGrade()
	if gradeTween then
		gradeTween:Cancel()
		gradeTween = nil
	end
	grade.Brightness = 0
	grade.Saturation = 0
	grade.Contrast = 0
end

local function hideAvatarDescendant(object: Instance)
	if object:IsA("BasePart") then
		if originalPartTransparency[object] == nil then
			originalPartTransparency[object] = object.LocalTransparencyModifier
		end
		object.LocalTransparencyModifier = 1
	elseif object:IsA("Decal") then
		if originalDecalTransparency[object] == nil then
			originalDecalTransparency[object] = object.Transparency
		end
		object.Transparency = 1
	end
end

local function hideAvatar(character: Model)
	for _, object in character:GetDescendants() do
		hideAvatarDescendant(object)
	end
	table.insert(connections, character.DescendantAdded:Connect(hideAvatarDescendant))
end

if player.Character then
	hideAvatar(player.Character)
end
table.insert(connections, player.CharacterAdded:Connect(hideAvatar))

RunService:BindToRenderStep(CAMERA_BINDING, Enum.RenderPriority.Camera.Value + 1, function()
	if not alive then
		return
	end
	local camera = Workspace.CurrentCamera
	if camera then
		camera.CameraType = Enum.CameraType.Scriptable
		camera.CFrame = CFrame.lookAt(CAMERA_POSITION, CAMERA_TARGET)
		camera.FieldOfView = CAMERA_FOV
	end
	-- Camera/player scripts can rewrite this local modifier. Reassert the test
	-- harness visibility without changing any effect Part's Transparency.
	for part in originalPartTransparency do
		if part.Parent then
			part.LocalTransparencyModifier = 1
		end
	end
end)

local function scheduleImpacts(version: number)
	if not impactPulses then
		return
	end
	for _, at in PULSE_TIMES do
		task.delay(at, function()
			if not alive or castVersion ~= version then
				return
			end
			resetGrade()
			grade.Saturation = -1
			grade.Brightness = 0.28
			grade.Contrast = 0.15
			gradeTween = TweenService:Create(grade, TweenInfo.new(0.12, Enum.EasingStyle.Quad, Enum.EasingDirection.Out), {
				Brightness = 0,
				Saturation = 0,
				Contrast = 0,
			})
			gradeTween:Play()
		end)
	end
end

local function playEffect(withImpacts: boolean): (Status, number)
	castVersion += 1
	local version = castVersion
	resetGrade()
	effect.stop()
	local result = effect.play()
	if withImpacts then
		scheduleImpacts(version)
	end
	return result, version
end

local state = effect.build(Workspace, Vector3.zero)
print("ENUMA_NATIVE_BUILD", HttpService:JSONEncode(state))

local existing = ReplicatedStorage:FindFirstChild("EnumaControl")
assert(not existing, "This isolated scene already has an EnumaControl")
local control = Instance.new("BindableFunction")
control.Name = "EnumaControl"
control:SetAttribute("DatakyEnumaPreview", true)
control.OnInvoke = function(action: string, at: number?): Status
	if action == "status" then
		local result = effect.status()
		result.preview_manual_control = manualControl
		result.preview_impact_pulses = impactPulses
		return result
	end
	manualControl = true
	if action == "play" then
		local result = playEffect(true)
		return result
	elseif action == "stop" then
		castVersion += 1
		resetGrade()
		return effect.stop()
	elseif action == "sample" then
		assert(at == nil or (type(at) == "number" and at == at and math.abs(at) < math.huge), "sample expects a finite number of seconds")
		local duration = tonumber(effect.status().duration) or 29.4
		local requested = math.clamp(at or 0, 0, math.max(0, duration - 1 / 30))
		local _, version = playEffect(false)
		if requested > 0 then
			task.wait(requested)
		end
		if not alive or castVersion ~= version then
			return { cancelled = true, requested_time = requested }
		end
		local ok, result = pcall(effect.pause)
		return {
			requested_time = requested,
			status = effect.status(),
			pause_supported = ok,
			pause_error = if ok then nil else tostring(result),
			sample_excludes_postprocess_pulses = true,
		}
	end
	error("EnumaControl supports play, stop, status and sample", 0)
end
control.Parent = ReplicatedStorage

automaticThread = task.spawn(function()
	task.wait(2)
	while alive do
		if manualControl then
			task.wait(0.25)
		else
			playEffect(true)
			task.wait(REPEAT_SECONDS)
		end
	end
end)

script.Destroying:Connect(function()
	alive = false
	castVersion += 1
	if automaticThread and automaticThread ~= coroutine.running() then
		task.cancel(automaticThread)
	end
	RunService:UnbindFromRenderStep(CAMERA_BINDING)
	for _, connection in connections do
		connection:Disconnect()
	end
	for part, value in originalPartTransparency do
		if part.Parent then
			part.LocalTransparencyModifier = value
		end
	end
	for decal, value in originalDecalTransparency do
		if decal.Parent then
			decal.Transparency = value
		end
	end
	if savedCamera and savedCamera.Parent then
		if savedCameraType then savedCamera.CameraType = savedCameraType end
		if savedCameraFrame then savedCamera.CFrame = savedCameraFrame end
		if savedCameraFov then savedCamera.FieldOfView = savedCameraFov end
	end
	resetGrade()
	grade:Destroy()
	control:Destroy()
	effect.clear()
end)
