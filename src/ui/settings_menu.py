"""
Settings menu for configuring Factorio installation path and other settings.
"""
import pygame
import logging
import json
import sys
from pathlib import Path

try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False

try:
    from tkinter import filedialog
    import tkinter as tk
    root = None
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.constants import PYGAME_WINDOW_WIDTH, PYGAME_WINDOW_HEIGHT, get_factorio_graphics_path
from screen_manager import ScreenManager

CONFIG_FILE = Path(__file__).parent.parent.parent.parent / "config.json"

class SettingsMenu:
    """Settings menu for the blueprint generator."""
    
    def __init__(self):
        self.screen_manager = ScreenManager()
        self.width = PYGAME_WINDOW_WIDTH
        self.height = PYGAME_WINDOW_HEIGHT
        self.screen = self.screen_manager.get_screen()
        self.screen_manager.set_caption("Settings - Factorio Blueprint Generator")
        
        self.logger = logging.getLogger(__name__)
        
        # Colors
        self.bg_color = (40, 40, 50)
        self.title_color = (255, 200, 50)
        self.text_color = (255, 255, 255)
        self.input_bg_color = (60, 60, 70)
        self.input_text_color = (255, 255, 255)
        self.button_color = (60, 90, 150)
        self.button_hover_color = (80, 120, 200)
        self.button_text_color = (255, 255, 255)
        self.error_color = (255, 100, 100)
        self.success_color = (100, 255, 100)
        
        # Fonts
        self.title_font = pygame.font.Font(None, 72)
        self.label_font = pygame.font.Font(None, 32)
        self.input_font = pygame.font.Font(None, 28)
        self.button_font = pygame.font.Font(None, 36)
        self.info_font = pygame.font.Font(None, 24)
        
        # Load settings
        self.settings = self.load_settings()
        self.factorio_path = self.settings.get("factorio_install_path", 
            r"C:\Program Files (x86)\Steam\steamapps\common\Factorio")
        
        # Input state
        self.active_field = None
        self.message = ""
        self.message_color = self.text_color
        
        # Text selection state
        self.selection_start = 0
        self.selection_end = 0
        self.cursor_pos = 0
        self.is_selecting = False
        
    def load_settings(self):
        """Load settings from config file."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Failed to load config: {e}")
        return {}
    
    def save_settings(self):
        """Save settings to config file."""
        try:
            self.settings["factorio_install_path"] = self.factorio_path
            # Also save the computed graphics path for backward compatibility
            graphics_path = get_factorio_graphics_path(self.factorio_path)
            self.settings["factorio_graphics_path"] = graphics_path
            
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.settings, f, indent=4)
            
            self.message = "Settings saved successfully!"
            self.message_color = self.success_color
            return True
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")
            self.message = f"Failed to save: {e}"
            self.message_color = self.error_color
            return False
    
    def browse_folder(self):
        """Open folder browser dialog to select Factorio installation."""
        if not HAS_TKINTER:
            self.message = "Folder browser not available (tkinter not installed)"
            self.message_color = self.error_color
            return
        
        try:
            # Hide the pygame window temporarily by minimizing
            self.screen_manager.set_caption("")
            
            # Create a hidden tkinter root window
            global root
            if root is not None:
                root.destroy()
            root = tk.Tk()
            root.withdraw()  # Hide the main window
            
            # Open folder dialog
            folder_path = filedialog.askdirectory(
                title="Select Factorio Installation Folder",
                initialdir=self.factorio_path if Path(self.factorio_path).exists() else "C:\\"
            )
            
            root.destroy()
            
            if folder_path:  # User selected a folder
                self.factorio_path = folder_path
                self.cursor_pos = len(self.factorio_path)
                self.selection_start = self.cursor_pos
                self.selection_end = self.cursor_pos
                # Auto-test the path
                self.test_path()
                
            # Restore pygame window
            self.screen_manager.set_caption("Settings - Factorio Blueprint Generator")
        except Exception as e:
            self.logger.error(f"Failed to browse folder: {e}")
            self.message = f"Folder browser error: {e}"
            self.message_color = self.error_color
            if root is not None:
                root.destroy()
    
    def test_path(self):
        """Test if the Factorio path is valid."""
        path = Path(self.factorio_path)
        if path.exists() and path.is_dir():
            # Check if it looks like a Factorio directory
            expected_graphics = path / "data" / "base" / "graphics" / "entity"
            if expected_graphics.exists():
                self.message = "✓ Path is valid! Graphics found."
                self.message_color = self.success_color
                return True
            else:
                self.message = "⚠ Found directory but graphics not found. Check if this is a Factorio install."
                self.message_color = self.error_color
                return False
        else:
            self.message = "✗ Path not found!"
            self.message_color = self.error_color
            return False
    
    def handle_text_input(self, event):
        """Handle text input for the active field with selection and clipboard support."""
        if self.active_field is None:
            return
        
        if event.type == pygame.KEYDOWN:
            # Handle Ctrl+A (select all)
            if event.key == pygame.K_a and pygame.key.get_mods() & pygame.KMOD_CTRL:
                if self.active_field == "factorio_path":
                    self.selection_start = 0
                    self.selection_end = len(self.factorio_path)
                    self.cursor_pos = len(self.factorio_path)
                    return
            
            # Handle Ctrl+C (copy)
            elif event.key == pygame.K_c and pygame.key.get_mods() & pygame.KMOD_CTRL:
                if self.active_field == "factorio_path" and abs(self.selection_end - self.selection_start) > 0:
                    try:
                        start = min(self.selection_start, self.selection_end)
                        end = max(self.selection_start, self.selection_end)
                        selected_text = self.factorio_path[start:end]
                        if HAS_PYPERCLIP:
                            pyperclip.copy(selected_text)
                        else:
                            pygame.scrap.init()
                            pygame.scrap.put(pygame.SCRAP_TEXT, selected_text.encode())
                    except Exception:
                        # Clipboard not available, ignore
                        pass
                    return
            
            # Handle Ctrl+V (paste)
            elif event.key == pygame.K_v and pygame.key.get_mods() & pygame.KMOD_CTRL:
                if self.active_field == "factorio_path":
                    try:
                        if HAS_PYPERCLIP:
                            pasted_text = pyperclip.paste()
                        else:
                            pygame.scrap.init()
                            if pygame.scrap.contains(pygame.SCRAP_TEXT):
                                pasted_text = pygame.scrap.get(pygame.SCRAP_TEXT).decode()
                            else:
                                return
                        
                        # Delete selected text if any
                        if abs(self.selection_end - self.selection_start) > 0:
                            start = min(self.selection_start, self.selection_end)
                            end = max(self.selection_start, self.selection_end)
                            self.factorio_path = self.factorio_path[:start] + pasted_text + self.factorio_path[end:]
                            self.cursor_pos = start + len(pasted_text)
                        else:
                            # Insert at cursor
                            self.factorio_path = self.factorio_path[:self.cursor_pos] + pasted_text + self.factorio_path[self.cursor_pos:]
                            self.cursor_pos += len(pasted_text)
                        self.selection_start = self.cursor_pos
                        self.selection_end = self.cursor_pos
                    except Exception:
                        # Clipboard not available, ignore
                        pass
                    return
            
            # Handle Ctrl+X (cut)
            elif event.key == pygame.K_x and pygame.key.get_mods() & pygame.KMOD_CTRL:
                if self.active_field == "factorio_path" and abs(self.selection_end - self.selection_start) > 0:
                    try:
                        start = min(self.selection_start, self.selection_end)
                        end = max(self.selection_start, self.selection_end)
                        selected_text = self.factorio_path[start:end]
                        if HAS_PYPERCLIP:
                            pyperclip.copy(selected_text)
                        else:
                            pygame.scrap.init()
                            pygame.scrap.put(pygame.SCRAP_TEXT, selected_text.encode())
                        self.factorio_path = self.factorio_path[:start] + self.factorio_path[end:]
                        self.cursor_pos = start
                        self.selection_start = start
                        self.selection_end = start
                    except Exception:
                        # Clipboard not available, ignore
                        pass
                    return
            
            # Handle arrow keys for cursor movement
            elif event.key == pygame.K_LEFT:
                if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                    # Shift+Left: extend selection
                    self.cursor_pos = max(0, self.cursor_pos - 1)
                    self.selection_end = self.cursor_pos
                else:
                    # Move cursor left
                    self.cursor_pos = max(0, self.cursor_pos - 1)
                    self.selection_start = self.cursor_pos
                    self.selection_end = self.cursor_pos
                return
            elif event.key == pygame.K_RIGHT:
                if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                    # Shift+Right: extend selection
                    self.cursor_pos = min(len(self.factorio_path), self.cursor_pos + 1)
                    self.selection_end = self.cursor_pos
                else:
                    # Move cursor right
                    self.cursor_pos = min(len(self.factorio_path), self.cursor_pos + 1)
                    self.selection_start = self.cursor_pos
                    self.selection_end = self.cursor_pos
                return
            
            # Handle Home key
            elif event.key == pygame.K_HOME:
                self.cursor_pos = 0
                self.selection_start = 0
                self.selection_end = 0
                return
            
            # Handle End key
            elif event.key == pygame.K_END:
                self.cursor_pos = len(self.factorio_path)
                self.selection_start = self.cursor_pos
                self.selection_end = self.cursor_pos
                return
            
            # Handle Backspace
            elif event.key == pygame.K_BACKSPACE:
                if self.active_field == "factorio_path":
                    if abs(self.selection_end - self.selection_start) > 0:
                        # Delete selected text
                        start = min(self.selection_start, self.selection_end)
                        end = max(self.selection_start, self.selection_end)
                        self.factorio_path = self.factorio_path[:start] + self.factorio_path[end:]
                        self.cursor_pos = start
                    elif self.cursor_pos > 0:
                        # Delete character before cursor
                        self.factorio_path = self.factorio_path[:self.cursor_pos-1] + self.factorio_path[self.cursor_pos:]
                        self.cursor_pos -= 1
                    self.selection_start = self.cursor_pos
                    self.selection_end = self.cursor_pos
            
            # Handle Delete key
            elif event.key == pygame.K_DELETE:
                if self.active_field == "factorio_path":
                    if abs(self.selection_end - self.selection_start) > 0:
                        # Delete selected text
                        start = min(self.selection_start, self.selection_end)
                        end = max(self.selection_start, self.selection_end)
                        self.factorio_path = self.factorio_path[:start] + self.factorio_path[end:]
                        self.cursor_pos = start
                    elif self.cursor_pos < len(self.factorio_path):
                        # Delete character after cursor
                        self.factorio_path = self.factorio_path[:self.cursor_pos] + self.factorio_path[self.cursor_pos+1:]
                    self.selection_start = self.cursor_pos
                    self.selection_end = self.cursor_pos
            
            # Handle Return (Enter)
            elif event.key == pygame.K_RETURN:
                self.active_field = None
            
            # Handle normal character input
            else:
                if event.unicode.isprintable() and not (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    if self.active_field == "factorio_path":
                        if abs(self.selection_end - self.selection_start) > 0:
                            # Replace selected text
                            start = min(self.selection_start, self.selection_end)
                            end = max(self.selection_start, self.selection_end)
                            self.factorio_path = self.factorio_path[:start] + event.unicode + self.factorio_path[end:]
                            self.cursor_pos = start + 1
                        else:
                            # Insert at cursor
                            self.factorio_path = self.factorio_path[:self.cursor_pos] + event.unicode + self.factorio_path[self.cursor_pos:]
                            self.cursor_pos += 1
                        self.selection_start = self.cursor_pos
                        self.selection_end = self.cursor_pos
    
    def _draw_text_with_selection(self, text, rect):
        """Draw text with selection highlighting and cursor."""
        padding = 10
        text_x = rect.x + padding
        text_y = rect.y + 12
        
        # Calculate cursor and selection positions
        selection_start = min(self.selection_start, self.selection_end)
        selection_end = max(self.selection_start, self.selection_end)
        
        # If there's a selection, draw it with highlight
        if selection_end != selection_start:
            # Draw text before selection
            if selection_start > 0:
                before_text = text[:selection_start]
                before_surface = self.input_font.render(before_text, True, self.input_text_color)
                self.screen.blit(before_surface, (text_x, text_y))
                text_x += before_surface.get_width()
            
            # Draw selected text with background
            selected_text = text[selection_start:selection_end]
            selected_surface = self.input_font.render(selected_text, True, self.input_text_color)
            
            # Draw highlight background
            highlight_rect = pygame.Rect(text_x, rect.y + 5, selected_surface.get_width(), rect.height - 10)
            pygame.draw.rect(self.screen, (100, 150, 255), highlight_rect)
            
            # Draw highlighted text
            self.screen.blit(selected_surface, (text_x, text_y))
            text_x += selected_surface.get_width()
            
            # Draw text after selection
            if selection_end < len(text):
                after_text = text[selection_end:]
                after_surface = self.input_font.render(after_text, True, self.input_text_color)
                self.screen.blit(after_surface, (text_x, text_y))
        else:
            # No selection, just draw the text
            text_surface = self.input_font.render(text, True, self.input_text_color)
            self.screen.blit(text_surface, (text_x, text_y))
            cursor_x = text_x + text_surface.get_width()
        
        # Draw cursor
        text_surface = self.input_font.render(text[:self.cursor_pos], True, self.input_text_color)
        cursor_x = rect.x + padding + text_surface.get_width()
        pygame.draw.line(self.screen, self.input_text_color,
                        (cursor_x, rect.y + 10),
                        (cursor_x, rect.y + 40), 2)
    
    def draw(self):
        """Draw the settings menu."""
        self.screen.fill(self.bg_color)
        
        # Draw title
        title_text = "Settings"
        title_surface = self.title_font.render(title_text, True, self.title_color)
        title_rect = title_surface.get_rect(center=(self.width // 2, 60))
        self.screen.blit(title_surface, title_rect)
        
        # Draw input field for Factorio path
        y_offset = 150
        
        # Label
        label_text = "Factorio Installation Path:"
        label_surface = self.label_font.render(label_text, True, self.text_color)
        self.screen.blit(label_surface, (50, y_offset))
        
        # Helper text
        helper_text = "(e.g., C:\\Program Files (x86)\\Steam\\steamapps\\common\\Factorio)"
        helper_surface = self.info_font.render(helper_text, True, (150, 150, 150))
        self.screen.blit(helper_surface, (50, y_offset - 25))
        
        # Input box (make it narrower to fit Browse button)
        input_rect = pygame.Rect(50, y_offset + 40, self.width - 240, 50)
        pygame.draw.rect(self.screen, self.input_bg_color, input_rect)
        pygame.draw.rect(self.screen, 
                        (255, 255, 255) if self.active_field == "factorio_path" else (100, 100, 100),
                        input_rect, width=2)
        
        # Draw text with selection highlighting and cursor
        if self.active_field == "factorio_path":
            self._draw_text_with_selection(self.factorio_path, input_rect)
        else:
            # Just draw the text
            input_surface = self.input_font.render(self.factorio_path, True, self.input_text_color)
            self.screen.blit(input_surface, (input_rect.x + 10, input_rect.y + 12))
        
        # Browse button
        mouse_pos = pygame.mouse.get_pos()
        browse_rect = pygame.Rect(input_rect.right + 10, y_offset + 40, 120, 50)
        is_hovered = browse_rect.collidepoint(mouse_pos)
        browse_color = self.button_hover_color if is_hovered else self.button_color
        pygame.draw.rect(self.screen, browse_color, browse_rect, border_radius=5)
        pygame.draw.rect(self.screen, (255, 255, 255), browse_rect, width=2, border_radius=5)
        
        browse_text = self.button_font.render("Browse...", True, self.button_text_color)
        browse_text_rect = browse_text.get_rect(center=browse_rect.center)
        self.screen.blit(browse_text, browse_text_rect)
        
        # Draw buttons
        button_y = 350
        button_height = 50
        button_width = 200
        button_spacing = 20
        
        # Test Path button
        test_rect = pygame.Rect((self.width - button_width * 3 - button_spacing * 2) // 2, 
                               button_y, button_width, button_height)
        button_color = self.button_hover_color if pygame.mouse.get_focused() else self.button_color
        pygame.draw.rect(self.screen, button_color, test_rect, border_radius=10)
        pygame.draw.rect(self.screen, (255, 255, 255), test_rect, width=2, border_radius=10)
        
        test_text = self.button_font.render("Test Path", True, self.button_text_color)
        test_text_rect = test_text.get_rect(center=test_rect.center)
        self.screen.blit(test_text, test_text_rect)
        
        # Save button
        save_rect = pygame.Rect(test_rect.right + button_spacing, button_y,
                               button_width, button_height)
        pygame.draw.rect(self.screen, button_color, save_rect, border_radius=10)
        pygame.draw.rect(self.screen, (255, 255, 255), save_rect, width=2, border_radius=10)
        
        save_text = self.button_font.render("Save", True, self.button_text_color)
        save_text_rect = save_text.get_rect(center=save_rect.center)
        self.screen.blit(save_text, save_text_rect)
        
        # Back button
        back_rect = pygame.Rect(save_rect.right + button_spacing, button_y,
                               button_width, button_height)
        pygame.draw.rect(self.screen, button_color, back_rect, border_radius=10)
        pygame.draw.rect(self.screen, (255, 255, 255), back_rect, width=2, border_radius=10)
        
        back_text = self.button_font.render("Back", True, self.button_text_color)
        back_text_rect = back_text.get_rect(center=back_rect.center)
        self.screen.blit(back_text, back_text_rect)
        
        # Draw message
        if self.message:
            msg_surface = self.info_font.render(self.message, True, self.message_color)
            msg_rect = msg_surface.get_rect(center=(self.width // 2, 450))
            self.screen.blit(msg_surface, msg_rect)
        
        # Draw instructions
        instructions = [
            "Click on the input field to edit",
            "Tab: Focus input | Enter: Confirm | Esc: Back to menu"
        ]
        for i, instruction in enumerate(instructions):
            inst_surface = self.info_font.render(instruction, True, (150, 150, 150))
            self.screen.blit(inst_surface, (self.width - inst_surface.get_width() - 20, 
                                          self.height - 60 + i * 25))
    
    def handle_events(self):
        """Handle menu events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "exit"
            
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return "back"
                elif event.key == pygame.K_TAB:
                    # Toggle input focus
                    if self.active_field == "factorio_path":
                        self.active_field = None
                    else:
                        self.active_field = "factorio_path"
                        # Initialize cursor position at end of text
                        self.cursor_pos = len(self.factorio_path)
                        self.selection_start = self.cursor_pos
                        self.selection_end = self.cursor_pos
                else:
                    self.handle_text_input(event)
            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    mouse_pos = pygame.mouse.get_pos()
                    
                    # Check if clicking input field
                    input_rect = pygame.Rect(50, 190, self.width - 240, 50)
                    if input_rect.collidepoint(mouse_pos):
                        self.active_field = "factorio_path"
                        # Initialize cursor position at end of text
                        if self.cursor_pos == 0:
                            self.cursor_pos = len(self.factorio_path)
                            self.selection_start = self.cursor_pos
                            self.selection_end = self.cursor_pos
                    else:
                        self.active_field = None
                    
                    # Check Browse button
                    browse_rect = pygame.Rect(input_rect.right + 10, 190, 120, 50)
                    if browse_rect.collidepoint(mouse_pos):
                        self.browse_folder()
                        continue
                    
                    # Check buttons
                    button_y = 350
                    button_width = 200
                    button_spacing = 20
                    
                    test_rect = pygame.Rect((self.width - button_width * 3 - button_spacing * 2) // 2, 
                                           button_y, button_width, 50)
                    save_rect = pygame.Rect(test_rect.right + button_spacing, button_y,
                                           button_width, 50)
                    back_rect = pygame.Rect(save_rect.right + button_spacing, button_y,
                                           button_width, 50)
                    
                    if test_rect.collidepoint(mouse_pos):
                        self.test_path()
                    elif save_rect.collidepoint(mouse_pos):
                        if self.test_path():
                            if self.save_settings():
                                # Update constants
                                # This is a hack - would need to reload module
                                pass
                    elif back_rect.collidepoint(mouse_pos):
                        return "back"
        
        return None
    
    def run(self):
        """Run the settings menu."""
        running = True
        result = None
        
        while running and result is None:
            # Handle events
            result = self.handle_events()
            
            # Draw menu
            self.draw()
            
            self.screen_manager.flip()
            self.screen_manager.tick(60)
        
        return result

