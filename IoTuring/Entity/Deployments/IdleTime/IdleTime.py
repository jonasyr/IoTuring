import re
from IoTuring.Entity.Entity import Entity
from IoTuring.Entity.EntityData import EntitySensor
from IoTuring.MyApp.SystemConsts import OperatingSystemDetection as OsD
from IoTuring.MyApp.SystemConsts import DesktopEnvironmentDetection as De

KEY_IS_ACTIVE = 'is_active'


class IdleTime(Entity):
    NAME = "IdleTime"

    def Initialize(self):
        self.RegisterEntitySensor(EntitySensor(self, KEY_IS_ACTIVE))

    def Update(self):
        is_active = self._check_hyprland_active()
        self.SetEntitySensorValue(KEY_IS_ACTIVE, is_active)

    def _check_hyprland_active(self) -> bool:
        """
        User is active if:
        - hyprlock is NOT running, AND
        - At least one display has DPMS on
        """
        # Check if locked
        result = self.RunCommand("pidof hyprlock")
        if result.stdout and result.stdout.strip():
            return False

        # Check display DPMS status
        result = self.RunCommand("hyprctl monitors")
        if result.stdout:
            dpms_statuses = re.findall(r'dpmsStatus:\s*(\d+)', result.stdout)
            if dpms_statuses:
                # Active if any display is on (dpmsStatus: 1)
                return any(status == '1' for status in dpms_statuses)

        return True

    @classmethod
    def CheckSystemSupport(cls):
        if not (OsD.IsLinux() and De.IsWayland() and OsD.CommandExists("hyprctl")):
            raise Exception("This entity requires Hyprland on Wayland")
