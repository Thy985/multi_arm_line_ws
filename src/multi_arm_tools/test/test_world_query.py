"""Tests for world query module."""

from unittest.mock import MagicMock

from multi_arm_tools.world_query import WorldQuery


def test_world_query_import():
    """Test WorldQuery can be imported."""
    assert WorldQuery is not None


def test_world_query_print_objects(capsys):
    """Test printing objects list."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    obj1 = MagicMock()
    obj1.object_id = "red_cube"
    obj1.object_type = "cube"
    obj1.pose.position = [0.42, 0.15, 0.05]
    obj1.grasp_state = "FREE"
    obj1.attached_to = ""
    obj1.confidence = 0.94
    mock_response.object_states = [obj1]
    mock_response.relations = []
    mock_client.query_world.return_value = mock_response

    WorldQuery(mock_client).print_world()
    captured = capsys.readouterr()
    assert "red_cube" in captured.out
    assert "FREE" in captured.out


def test_world_query_print_object_detail(capsys):
    """Test printing single object detail."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    obj1 = MagicMock()
    obj1.object_id = "red_cube"
    obj1.object_type = "cube"
    obj1.pose.position = [0.42, 0.15, 0.05]
    obj1.pose.orientation = [0.0, 0.0, 0.0, 1.0]
    obj1.grasp_state = "FREE"
    obj1.attached_to = ""
    obj1.confidence = 0.94
    mock_response.object_states = [obj1]
    mock_response.relations = []
    mock_client.query_world.return_value = mock_response

    WorldQuery(mock_client).print_world("red_cube")
    captured = capsys.readouterr()
    assert "red_cube" in captured.out
    assert "cube" in captured.out
    assert "FREE" in captured.out
    assert "0.94" in captured.out


def test_world_query_print_relations(capsys):
    """Test printing relations."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.object_states = []
    rel1 = MagicMock()
    rel1.subject = "red_cube"
    rel1.predicate = "ON"
    rel1.object = "table"
    rel1.confidence = 0.95
    rel1.distance = 0.05
    mock_response.relations = [rel1]
    mock_client.query_world.return_value = mock_response

    WorldQuery(mock_client).print_world(show_relations=True)
    captured = capsys.readouterr()
    assert "red_cube" in captured.out
    assert "ON" in captured.out
    assert "table" in captured.out


def test_world_query_no_objects(capsys):
    """Test when no objects in world."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.object_states = []
    mock_response.relations = []
    mock_client.query_world.return_value = mock_response

    WorldQuery(mock_client).print_world()
    captured = capsys.readouterr()
    assert "No objects" in captured.out


def test_world_query_object_not_found(capsys):
    """Test when requested object not found."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.object_states = []
    mock_response.relations = []
    mock_client.query_world.return_value = mock_response

    WorldQuery(mock_client).print_world("nonexistent")
    captured = capsys.readouterr()
    assert "not found" in captured.out