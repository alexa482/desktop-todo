import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from app import TodoApp, PhotoBackground, MESSAGES, QUOTE_DURATION_MS, QUOTE_FADE_STEPS, QUOTE_COLOR, PANEL_COLOR, mix_color, discover_photos, prepare_photo, find_photo, Image, BACKGROUND_DIMMING, TaskModel, load_data, normalize_data, task_label, write_data


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.model = TaskModel(normalize_data({"sections": {"General": []}}))

    def test_packaged_paths_and_first_launch_migration(self):
        import app
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / 'seed' / 'tasks.json'
            seed.parent.mkdir()
            original = json.dumps(self.model.data).encode()
            seed.write_bytes(original)
            target = root / 'user' / 'tasks.json'
            with patch.object(app.sys, 'frozen', True, create=True), \
                 patch.object(app.sys, '_MEIPASS', str(root), create=True), \
                 patch.object(Path, 'home', return_value=root):
                self.assertEqual(app.resource_path('assets', 'backgrounds'), root / 'assets' / 'backgrounds')
                self.assertEqual(app.task_data_path(), root / 'Library' / 'Application Support' / 'My To Do List' / 'tasks.json')
                app.initialize_user_data(target)
                self.assertEqual(target.read_bytes(), original)
                target.write_text('existing user data')
                app.initialize_user_data(target)
                self.assertEqual(target.read_text(), 'existing user data')
                self.assertEqual(seed.read_bytes(), original)

    def test_section_order_migration_repair_and_new_sections(self):
        legacy = {'sections': {'General': [], 'HRI': [], 'VR/AR': []}}
        data = normalize_data(legacy)
        self.assertEqual(data['section_order'], ['General', 'HRI', 'VR/AR'])
        legacy['section_order'] = ['VR/AR', 'VR/AR', 'missing', None]
        repaired = normalize_data(legacy)
        self.assertEqual(repaired['section_order'], ['VR/AR', 'General', 'HRI'])
        model = TaskModel(repaired)
        model.add_section('Spanish')
        self.assertEqual(model.data['section_order'], ['VR/AR', 'General', 'HRI', 'Spanish'])

    def test_reorder_persistence_preserves_tasks_counts_and_selection(self):
        import copy
        self.model.add_task('General task')
        self.model.add_section('HRI')
        main = self.model.add_task('Assignment')
        child = self.model.add_task('Subtask', parent=main)
        self.model.add_task('Nested', parent=child)
        self.model.complete(main)
        self.model.add_section('VR/AR')
        before = copy.deepcopy(self.model.data['sections'])
        self.model.reorder_sections(['VR/AR', 'General', 'HRI'])
        self.assertEqual(self.model.data['sections'], before)
        self.assertEqual(self.model.data['selected_section'], 'VR/AR')
        self.assertEqual(self.model.incomplete_count('General'), 1)
        self.assertEqual(self.model.incomplete_count('HRI'), 0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tasks.json'
            write_data(path, self.model.data)
            loaded = load_data(path)
            self.assertEqual(loaded['section_order'], ['VR/AR', 'General', 'HRI'])
            self.assertEqual(loaded['sections'], before)
        for order in (['General'], ['General', 'General', 'HRI']):
            with self.assertRaises(ValueError):
                self.model.reorder_sections(order)

    def test_section_drag_preview_drop_and_plain_click(self):
        from types import SimpleNamespace
        app = TodoApp.__new__(TodoApp)
        app.model = TaskModel(normalize_data({'sections': {'General': [], 'HRI': [], 'VR/AR': []}}))
        app.section_names = {'a': 'General', 'b': 'HRI', 'c': 'VR/AR'}
        app.section_list = Mock()
        app.save_tasks = Mock()
        tree = app.section_list
        tree.identify_row.return_value = 'c'
        tree.winfo_height.return_value = 300
        app.section_drag_start(SimpleNamespace(y=75))
        app.section_drag_motion(SimpleNamespace(y=77))
        tree.move.assert_not_called()
        app.section_drag_end(SimpleNamespace(y=77))
        app.save_tasks.assert_not_called()
        app.section_drag_start(SimpleNamespace(y=75))
        tree.identify_row.return_value = 'a'
        tree.get_children.return_value = ('a', 'b', 'c')
        tree.bbox.return_value = (0, 0, 200, 30)
        app.section_drag_motion(SimpleNamespace(y=10))
        tree.move.assert_called_with('c', '', 0)
        # Preview only: persistent order is committed on release.
        self.assertEqual(app.model.data['section_order'], ['General', 'HRI', 'VR/AR'])
        tree.get_children.return_value = ('c', 'a', 'b')
        app.section_drag_end(SimpleNamespace(y=10))
        self.assertEqual(app.model.data['section_order'], ['VR/AR', 'General', 'HRI'])
        app.save_tasks.assert_called_once()
        self.assertIsNone(app.section_drag)

    def test_section_isolation_and_validation(self):
        self.model.add_task("General task")
        self.model.add_section(" HRI ")
        self.assertEqual(self.model.tasks, [])
        self.model.add_task("Lab 2")
        self.model.add_section("Spanish")
        self.assertEqual(self.model.tasks, [])
        self.assertEqual(self.model.data['sections']['HRI'][0]['text'], 'Lab 2')
        for name in ('', '   ', 'hri'):
            with self.assertRaises(ValueError):
                self.model.add_section(name)
        self.assertIsNone(self.model.add_task('   '))

    def test_independent_completion_and_deletion(self):
        parent = self.model.add_task('Assignment')
        first = self.model.add_task('Read paper', parent=(0,))
        second = self.model.add_task('Write intro', parent=(0,))
        self.model.complete(second)
        self.assertFalse(self.model.item(parent)['completed'])
        self.assertFalse(self.model.item(first)['completed'])
        self.model.complete(parent)
        self.model.complete(parent)
        self.assertFalse(self.model.item(first)['completed'])
        self.assertTrue(self.model.item(second)['completed'])
        self.model.delete(first)
        self.assertEqual(self.model.tasks[0]['subtasks'][0]['text'], 'Write intro')
        self.model.add_task('Study for Exam')
        self.model.delete(parent)
        self.assertEqual([task['text'] for task in self.model.tasks], ['Study for Exam'])
        self.assertEqual(self.model.tasks[0]['subtasks'], [])

    def test_bullets_are_presentation_only(self):
        location = self.model.add_task('Read paper')
        self.assertEqual(task_label(self.model.item(location)), '• Read paper')
        self.model.complete(location)
        self.assertEqual(task_label(self.model.item(location)), '✓ Read paper')
        self.assertEqual(self.model.item(location)['text'], 'Read paper')

    def test_round_trip_all_sections_and_empty_sections(self):
        self.model.add_section('HRI')
        self.model.add_task('Assignment')
        child = self.model.add_task('Read paper', parent=(0,))
        self.model.complete(child)
        self.model.add_section('VR/AR')
        self.model.add_task('Prototype')
        self.model.add_section('Spanish')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tasks.json'
            write_data(path, self.model.data)
            self.assertEqual(load_data(path), self.model.data)
            self.assertEqual(load_data(path)['selected_section'], 'Spanish')

    def test_migration_and_exact_backup(self):
        originals = [
            ['Old task', '✓ Done'],
            {'sections': {'HRI': ['Lab 2', '✓ Read'], 'Spanish': []},
             'selected_section': 'HRI'},
        ]
        for original in originals:
            with self.subTest(original=original), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'tasks.json'
                raw = json.dumps(original).encode()
                path.write_bytes(raw)
                data = load_data(path)
                tasks = data['sections'][data['selected_section']]
                self.assertFalse(tasks[0]['completed'])
                self.assertTrue(tasks[1]['completed'])
                self.assertFalse(tasks[1]['text'].startswith('✓ '))
                self.assertEqual(path.with_suffix('.json.bak').read_bytes(), raw)
                self.assertEqual(load_data(path), data)
                self.assertEqual(path.with_suffix('.json.bak').read_bytes(), raw)

    def test_missing_empty_and_invalid_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tasks.json'
            self.assertEqual(load_data(path)['sections'], {'General': []})
            path.write_text('')
            self.assertEqual(load_data(path)['sections'], {'General': []})
            invalid = ['{broken', '{"sections": {"HRI": [42]}}',
                       '{"version": 99, "sections": {"HRI": []}}']
            for raw in invalid:
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    load_data(path)
                self.assertEqual(path.read_text(), raw)

    def test_invalid_structured_tasks(self):
        invalid = [
            {'text': 'Task', 'completed': 'false'},
            {'text': 'Task', 'completed': False, 'subtasks': {}},
            {'text': 'Task', 'completed': False, 'subtasks': [
                {'text': 'Child', 'completed': False, 'subtasks': [
                    {'text': 'Grandchild', 'completed': False, 'subtasks': ['Too deep']}]} ]},
        ]
        for task in invalid:
            with self.assertRaises(ValueError):
                normalize_data({'sections': {'HRI': [task]}})

    def test_three_levels_toggle_counts_and_delete(self):
        main = self.model.add_task('Assignment')
        child = self.model.add_task('Build behavior', parent=main)
        leaf = self.model.add_task('Test head', parent=child)
        self.assertEqual(leaf, (0, 0, 0))
        with self.assertRaises(ValueError):
            self.model.add_task('Too deep', parent=leaf)
        for location in (leaf, child, main):
            self.model.toggle(location)
            self.assertTrue(self.model.item(location)['completed'])
            self.model.toggle(location)
            self.assertFalse(self.model.item(location)['completed'])
        self.model.toggle(leaf)
        self.model.toggle(child)
        self.assertEqual(self.model.incomplete_count('General'), 1)
        self.model.toggle(main)
        self.assertEqual(self.model.incomplete_count('General'), 0)
        self.model.toggle(main)
        self.assertEqual(self.model.incomplete_count('General'), 1)
        self.model.add_section('HRI')
        self.assertEqual(self.model.incomplete_count('General'), 1)
        self.assertEqual(self.model.incomplete_count('HRI'), 0)
        self.model.data['selected_section'] = 'General'
        self.model.delete(leaf)
        self.assertEqual(self.model.item(child)['subtasks'], [])
        self.model.add_task('Test antennas', parent=child)
        self.model.delete(child)
        self.assertEqual(self.model.item(main)['subtasks'], [])
        self.model.add_task('Report', parent=main)
        self.model.delete(main)
        self.assertEqual(self.model.tasks, [])
        self.assertEqual(self.model.incomplete_count('General'), 0)

    def test_v2_migration_and_three_level_persistence(self):
        original = {'version': 2, 'sections': {'HRI': [
            {'text': 'Assignment', 'completed': True, 'subtasks': [
                {'text': 'Build behavior', 'completed': False}]}]}, 'selected_section': 'HRI'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tasks.json'
            path.with_suffix('.json.bak').write_text('older backup')
            raw = json.dumps(original)
            path.write_text(raw)
            model = TaskModel(load_data(path))
            self.assertEqual(path.with_suffix('.json.pre-v3.bak').read_text(), raw)
            self.assertEqual(path.with_suffix('.json.bak').read_text(), 'older backup')
            self.assertTrue(model.item((0,))['completed'])
            self.assertEqual(model.item((0, 0))['text'], 'Build behavior')
            leaf = model.add_task('Test antennas', parent=(0, 0))
            model.toggle(leaf)
            write_data(path, model.data)
            self.assertEqual(load_data(path), model.data)
            model.toggle(leaf)
            write_data(path, model.data)
            self.assertFalse(load_data(path)['sections']['HRI'][0]['subtasks'][0]['subtasks'][0]['completed'])

    def test_recursive_rendering_and_depth_controls(self):
        main = self.model.add_task('Assignment')
        child = self.model.add_task('Build behavior', parent=main)
        leaf = self.model.add_task('Test head', parent=child)
        app = TodoApp.__new__(TodoApp)
        app.model = self.model
        app.locations = {}
        app.heading = Mock()
        app.task_tree = Mock()
        app.task_tree.get_children.return_value = []
        app.task_tree.insert.side_effect = ['main', 'child', 'leaf']
        app.refresh_sections = Mock()
        app.update_actions = Mock()
        app.show_section(leaf)
        calls = app.task_tree.insert.call_args_list
        self.assertEqual([call.args[0] for call in calls], ['', 'main', 'child'])
        self.assertEqual(app.locations, {'main': main, 'child': child, 'leaf': leaf})
        app.task_tree.selection_set.assert_called_with('leaf')
        app.subtask_button = Mock()
        app.complete_button = Mock()
        app.delete_button = Mock()
        for location, expected in ((main, 'normal'), (child, 'normal'), (leaf, 'disabled')):
            app.selected_location = Mock(return_value=location)
            TodoApp.update_actions(app)
            app.subtask_button.configure.assert_called_with(state=expected)

    def test_double_click_targets_row_and_ignores_arrows_and_blanks(self):
        app = TodoApp.__new__(TodoApp)
        app.task_tree = Mock()
        app.complete_task = Mock()
        event = Mock(x=50, y=70)
        app.task_tree.identify_row.return_value = 'leaf'
        app.task_tree.identify_element.return_value = 'text'
        self.assertEqual(app.double_click(event), 'break')
        app.task_tree.selection_set.assert_called_with('leaf')
        app.complete_task.assert_called_once_with(toggle=True)
        app.complete_task.reset_mock()
        app.task_tree.identify_element.return_value = 'Treeitem.indicator'
        app.double_click(event)
        app.task_tree.identify_row.return_value = ''
        app.task_tree.identify_element.return_value = ''
        app.double_click(event)
        app.complete_task.assert_not_called()

    def test_toggle_handler_updates_count_and_saves(self):
        location = self.model.add_task('Assignment')
        app = TodoApp.__new__(TodoApp)
        app.model = self.model
        app.selected_location = Mock(return_value=location)
        app.task_tree = Mock()
        app.task_tree.selection.return_value = ('main',)
        app.refresh_sections = Mock()
        app.save_tasks = Mock()
        app.complete_task(toggle=True)
        self.assertEqual(self.model.incomplete_count('General'), 0)
        app.complete_task(toggle=True)
        self.assertEqual(self.model.incomplete_count('General'), 1)
        self.assertEqual(app.refresh_sections.call_count, 2)
        self.assertEqual(app.save_tasks.call_count, 2)
        app.task_tree.item.assert_called_with('main', text='• Assignment')

    def test_quote_rotation_and_shutdown(self):
        app = TodoApp.__new__(TodoApp)
        app.layout = Mock()
        app.root = Mock()
        app.background = Mock()
        app.message_label = Mock()
        app.message_index = 0
        displayed = [MESSAGES[0]]
        for _ in range(6):
            app.rotate_message()
            # Execute scheduled fade frames without creating a GUI or waiting.
            for _ in range(QUOTE_FADE_STEPS * 2):
                callback = app.root.after.call_args.args[1]
                callback()
            displayed.append(MESSAGES[app.message_index])
            app.root.after.assert_called_with(QUOTE_DURATION_MS, app.rotate_message)
            app.message_label.configure.assert_any_call(foreground=QUOTE_COLOR)
            app.message_label.configure.assert_called_with(state="normal")
        self.assertEqual(displayed, list(MESSAGES) + [MESSAGES[0]])
        colors = [call.kwargs.get('foreground') for call in app.message_label.configure.call_args_list]
        self.assertIn(PANEL_COLOR, colors)
        self.assertGreater(len(set(colors)), 10)
        app.close()
        app.root.after_cancel.assert_called_once_with(app.message_timer)
        app.background.close.assert_called_once()
        app.root.destroy.assert_called_once()

    @unittest.skipIf(Image is None, 'Pillow is not installed')
    def test_translucent_panels_preserve_photo_and_rounded_corners(self):
        from app import compose_panels, panel_bounds, PANEL_OPACITY
        photo = Image.new('RGB', (900, 650), 'white')
        composed = compose_panels(photo)
        self.assertEqual(composed.getpixel((10, 10)), (255, 255, 255))
        self.assertEqual(composed.getpixel((24, 28)), (255, 255, 255))
        expected = 255 - round(255 * PANEL_OPACITY)
        self.assertEqual(composed.getpixel((60, 60)), (expected,) * 3)
        self.assertEqual(photo.getpixel((60, 60)), (255,) * 3)
        self.assertEqual(panel_bounds((1000, 700))[1], (290, 28, 976, 672))

    def test_background_ignores_transient_one_pixel_startup_size(self):
        background = PhotoBackground.__new__(PhotoBackground)
        background.root = Mock()
        background.size = (800, 550)
        background.request = Mock()
        background.root.winfo_width.return_value = 1
        background.root.winfo_height.return_value = 1
        background.resize_to_window()
        self.assertEqual(background.size, (800, 550))
        background.request.assert_not_called()
        background.root.winfo_width.return_value = 960
        background.root.winfo_height.return_value = 640
        background.resize_to_window()
        self.assertEqual(background.size, (960, 640))
        background.request.assert_called_once_with(resize=True)

    def test_background_timer_replacement_and_cleanup(self):
        background = PhotoBackground.__new__(PhotoBackground)
        background.root = Mock()
        background.root.after.side_effect = ['timer1', 'timer2']
        background.timers = {}
        background.closed = False
        background.executor = Mock()
        callback = Mock()
        background.schedule('resize', 180, callback)
        background.schedule('resize', 180, callback)
        background.root.after_cancel.assert_called_with('timer1')
        background.close()
        background.root.after_cancel.assert_called_with('timer2')
        background.executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
        background.root.after.call_args.args[1]()
        callback.assert_not_called()

    def test_photo_discovery_and_fade_colors(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name in ('a.JPG', 'b.jpeg', 'c.PNG', 'notes.txt'):
                (folder / name).touch()
            (folder / 'directory.png').mkdir()
            self.assertEqual([p.name for p in discover_photos(folder)], ['a.JPG', 'b.jpeg', 'c.PNG'])
            self.assertEqual(discover_photos(folder / 'missing'), [])
        self.assertEqual(mix_color('#000000', '#ffffff', 0), '#000000')
        self.assertEqual(mix_color('#000000', '#ffffff', 1), '#ffffff')
        self.assertEqual(mix_color('#000000', '#ffffff', .5), '#808080')

    @unittest.skipIf(Image is None, 'Pillow is not installed')
    def test_photo_crop_dimming_and_corrupt_file_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            bad = folder / 'bad.jpg'
            bad.write_text('not an image')
            good = folder / 'wide.png'
            image = Image.new('RGB', (200, 100), 'red')
            # Center square should fill a square viewport with no stretching.
            image.paste('white', (50, 0, 150, 100))
            image.save(good)
            path, photo = find_photo([bad, good], (50, 50))
            self.assertEqual(path, good)
            self.assertEqual(photo.size, (50, 50))
            expected = int(255 * (1 - BACKGROUND_DIMMING))
            self.assertEqual(photo.getpixel((25, 25)), (expected,) * 3)
            self.assertEqual(prepare_photo(good, (100, 30)).size, (100, 30))
            self.assertEqual(find_photo([bad], (50, 50)), (None, None))
            self.assertEqual(find_photo([], (50, 50)), (None, None))

    def test_failed_replace_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tasks.json'
            path.write_text('original')
            with patch.object(Path, 'replace', side_effect=OSError('failed')):
                with self.assertRaises(OSError):
                    write_data(path, self.model.data)
            self.assertEqual(path.read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
