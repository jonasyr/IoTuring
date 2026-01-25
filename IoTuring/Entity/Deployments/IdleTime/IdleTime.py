import os
import time
from IoTuring.Entity.Entity import Entity
from IoTuring.Entity.EntityData import EntitySensor
from IoTuring.Entity.ValueFormat import ValueFormatter, ValueFormatterOptions
from IoTuring.MyApp.SystemConsts import OperatingSystemDetection as OsD
from IoTuring.MyApp.SystemConsts import DesktopEnvironmentDetection as De

KEY_IDLE_TIME = 'idle_time'
KEY_IS_ACTIVE = 'is_active'

# Windows dep
try:
    import ctypes
    windows_support = True
except BaseException:
    windows_support = False

# macOS dep
try:
    from Quartz import CGEventSourceSecondsSinceLastEventType, kCGEventSourceStateHIDSystemState  # type: ignore
    macos_support = True
except BaseException:
    macos_support = False


class IdleTime(Entity):
    NAME = "IdleTime"

    def Initialize(self):
        # Sensor for idle time in seconds
        self.RegisterEntitySensor(
            EntitySensor(
                self, 
                KEY_IDLE_TIME, 
                valueFormatterOptions=ValueFormatterOptions(
                    ValueFormatterOptions.TYPE_TIME, 
                    0, 
                    "s"
                )
            )
        )
        
        # Binary sensor for active/inactive state (active if idle < 60 seconds)
        # Binary sensor configuration is handled in entities.yaml
        self.RegisterEntitySensor(EntitySensor(self, KEY_IS_ACTIVE))
        
        # Select appropriate update function based on OS
        UpdateFunction = {
            OsD.LINUX: self.GetIdleTime_Linux_Wayland if De.IsWayland() else self.GetIdleTime_Linux_X11,
            OsD.WINDOWS: self.GetIdleTime_Windows,
            OsD.MACOS: self.GetIdleTime_macOS
        }
        
        self.UpdateSpecificFunction = UpdateFunction[OsD.GetOs()]

    def Update(self):
        if self.UpdateSpecificFunction:
            idle_seconds = self.UpdateSpecificFunction()
            self.SetEntitySensorValue(KEY_IDLE_TIME, idle_seconds)
            
            # Set binary sensor: True if active (idle == 0), False if inactive (idle > 0)
            is_active = idle_seconds == 0
            self.SetEntitySensorValue(KEY_IS_ACTIVE, is_active)

    def GetIdleTime_macOS(self) -> float:
        try:
            return CGEventSourceSecondsSinceLastEventType(
                kCGEventSourceStateHIDSystemState,
                -1  # Any event type
            )
        except BaseException:
            return 0.0

    def GetIdleTime_Windows(self) -> float:
        try:
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [
                    ('cbSize', ctypes.c_uint),
                    ('dwTime', ctypes.c_uint),
                ]
            
            lastInputInfo = LASTINPUTINFO()
            lastInputInfo.cbSize = ctypes.sizeof(lastInputInfo)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lastInputInfo))
            
            millis = ctypes.windll.kernel32.GetTickCount() - lastInputInfo.dwTime
            return millis / 1000.0
        except BaseException:
            return 0.0

    def GetIdleTime_Linux_X11(self) -> float:
        # Use xprintidle command (returns milliseconds)
        p = self.RunCommand("xprintidle")
        
        if p.stdout:
            try:
                millis = int(p.stdout.strip())
                return millis / 1000.0
            except ValueError:
                pass
        
        return 0.0

    def GetIdleTime_Linux_Wayland(self) -> float:
        """
        Get idle time on Wayland/Hyprland systems.
        
        Strategy: Use system idle indicators rather than trying to detect
        individual input events:
        1. Check if screen is locked (hyprlock running)
        2. Check if displays are off (DPMS status)
        3. Track when these states change
        
        This gives a reliable "working vs away" state without needing
        to detect every keystroke.
        """
        
        current_time = time.time()
        
        # Initialize last_activity_time if not exists
        if not hasattr(self, 'last_activity_time'):
            self.last_activity_time = current_time
            return 0.0
        
        # Method 1: Check if screen is locked (user is definitely idle)
        is_locked = self._is_screen_locked()
        
        # Method 2: Check if displays are off (DPMS off = idle)
        is_dpms_off = self._are_displays_off()
        
        # If locked or displays off, user is idle
        if is_locked or is_dpms_off:
            # Don't update last_activity_time - let idle time increase
            return current_time - self.last_activity_time
        
        # User is active (not locked, displays on)
        # Reset activity timer
        self.last_activity_time = current_time
        return 0.0
    
    def _is_screen_locked(self) -> bool:
        """Check if hyprlock is running"""
        try:
            result = self.RunCommand("pidof hyprlock")
            return bool(result.stdout and result.stdout.strip())
        except Exception:
            return False
    
    def _are_displays_off(self) -> bool:
        """Check if all displays have DPMS off (dpmsStatus: 0)"""
        try:
            result = self.RunCommand("hyprctl monitors")
            if not result.stdout:
                return False
            
            # Parse DPMS status from all monitors
            # dpmsStatus: 1 means ON, dpmsStatus: 0 means OFF
            import re
            dpms_statuses = re.findall(r'dpmsStatus:\s*(\d+)', result.stdout)
            
            if not dpms_statuses:
                return False
            
            # If ANY display is on, user is active
            # If ALL displays are off, user is idle
            return all(status == '0' for status in dpms_statuses)
            
        except Exception:
            return False
        if OsD.CommandExists("hyprctl"):
            try:
                import json
                
                # Get active window info
                p = self.RunCommand("hyprctl activewindow -j")
                
                if p.stdout and p.stdout.strip():
                    data = json.loads(p.stdout)
                    
                    # Get unique window identifier
                    window_address = data.get('address', '')
                    window_title = data.get('title', '')
                    window_id = f"{window_address}:{window_title}"
                    
                    # Get cursor position
                    cursor_result = self.RunCommand("hyprctl cursorpos")
                    cursor_pos = cursor_result.stdout.strip() if cursor_result.stdout else ""
                    
                    # Initialize tracking variables if not exists
                    if not hasattr(self, 'last_window_id'):
                        self.last_window_id = window_id
                        self.last_cursor_pos = cursor_pos
                        self.last_cursor_change_time = current_time
                        self.last_activity_time = current_time
                        return 0.0
                    
                    # Check for any activity indicators
                    if window_id != self.last_window_id:
                        # Window or title changed
                        activity_detected = True
                        self.last_window_id = window_id
                    
                    if cursor_pos != self.last_cursor_pos and cursor_pos != "":
                        # Cursor moved - this is activity!
                        # Note: Even typing can cause tiny cursor movements
                        activity_detected = True
                        self.last_cursor_pos = cursor_pos
                        self.last_cursor_change_time = current_time
                    
            except Exception as e:
                pass
        
        # Update activity time if any activity detected
        if activity_detected:
            self.last_activity_time = current_time
            return 0.0
        
        # No activity detected, return time since last activity
        if not hasattr(self, 'last_activity_time'):
            self.last_activity_time = current_time
            return 0.0
        
        return current_time - self.last_activity_time
        
        # Try Sway
        if OsD.CommandExists("swaymsg"):
            try:
                import json
                p = self.RunCommand("swaymsg -t get_tree")
                
                if p.stdout:
                    data = json.loads(p.stdout)
                    
                    # Find focused window
                    def find_focused(node):
                        if node.get('focused'):
                            return node.get('id', ''), node.get('name', '')
                        for child in node.get('nodes', []) + node.get('floating_nodes', []):
                            result = find_focused(child)
                            if result[0]:
                                return result
                        return '', ''
                    
                    window_id, window_name = find_focused(data)
                    window_identifier = f"{window_id}:{window_name}"
                    
                    # Initialize or check for changes
                    if not hasattr(self, 'last_window_id'):
                        self.last_window_id = window_identifier
                        self.last_activity_time = current_time
                        return 0.0
                    
                    if window_identifier != self.last_window_id:
                        self.last_window_id = window_identifier
                        self.last_activity_time = current_time
                        return 0.0
                    
                    return current_time - self.last_activity_time
                    
            except Exception:
                pass
        
        # Fallback: Just track time since last update
        if not hasattr(self, 'last_activity_time'):
            self.last_activity_time = current_time
            return 0.0
        
        return current_time - self.last_activity_time

    @classmethod
    def CheckSystemSupport(cls):
        if OsD.IsLinux():
            if De.IsWayland():
                # Wayland: Check for supported compositor commands
                has_hyprctl = OsD.CommandExists("hyprctl")
                has_swaymsg = OsD.CommandExists("swaymsg")
                
                if not (has_hyprctl or has_swaymsg):
                    raise Exception(
                        "Wayland idle detection requires:\n"
                        "  - hyprctl (Hyprland), or\n"
                        "  - swaymsg (Sway)"
                    )
            else:
                # X11: Require xprintidle
                if not OsD.CommandExists("xprintidle"):
                    raise Exception("X11 idle detection requires 'xprintidle' command")

        elif OsD.IsWindows() or OsD.IsMacos():
            if (OsD.IsWindows() and not windows_support) or\
                    (OsD.IsMacos() and not macos_support):
                raise Exception("Unsatisfied dependencies for this entity")

        else:
            raise cls.UnsupportedOsException()
