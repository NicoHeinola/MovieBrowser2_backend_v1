import os
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.orm import Session, selectinload
from typing import List, Optional, cast

from middleware.authenticated_route import authenticated_route, optionally_authenticated_route
from middleware.is_admin import is_admin
from middleware.query_parser import get_parsed_query_params
from models.setting import Setting
from models.user import User
from models.user_watch_season import UserWatchSeason as UserWatchSeasonModel
from models.user_watch_season import UserWatchSeason
from schemas.episode import Episode
from schemas.paginated_response import PaginatedResponse
from schemas.show import Show, ShowCreate, ShowUpdate
from models.show import Show as ShowModel
from database import get_db
from models.episode import Episode as EpisodeModel
from models.season import Season as SeasonModel
from utils.pagination import paginate_query
from utils.vlc_media_player_util import VLCMediaPlayerUtil

router = APIRouter()


@router.get("/export")
@authenticated_route
@is_admin
def export_shows(request: Request, db: Session = Depends(get_db)):
    """
    Export all show-related data in a migration-friendly payload.
    This includes shows, seasons, episodes, categories, and user progress links.
    """

    shows = (
        db.query(ShowModel)
        .options(
            selectinload(ShowModel.seasons).selectinload(SeasonModel.episodes),
            selectinload(ShowModel.categories),
            selectinload(ShowModel.user_show_statuses),
        )
        .all()
    )

    user_watch_seasons = db.query(UserWatchSeasonModel).all()

    users = db.query(User).all()
    users_by_id = {user.id: user for user in users}

    watch_seasons_by_show_id: dict[int, list[UserWatchSeasonModel]] = {}
    for user_watch_season in user_watch_seasons:
        show_id = cast(int, user_watch_season.show_id)
        if show_id not in watch_seasons_by_show_id:
            watch_seasons_by_show_id[show_id] = []
        watch_seasons_by_show_id[show_id].append(user_watch_season)

    exported_shows = []
    for show in shows:
        current_show_id = cast(int, show.id)
        show_folder_name = cast(str, show.folder_name)
        show_relative_folder_path = show_folder_name
        show_absolute_folder_path = show.get_full_folder_path()
        show_payload = {
            "id": current_show_id,
            "title": show.title,
            "description": show.description,
            "image": show.image,
            "folder_name": show_folder_name,
            "folder_path": {
                "relative": show_relative_folder_path,
                "absolute": show_absolute_folder_path,
            },
            "categories": [
                {
                    "id": category.id,
                    "name": category.name,
                }
                for category in show.categories
            ],
            "seasons": [],
            "user_show_statuses": [
                {
                    "id": user_show_status.id,
                    "user_id": cast(int, user_show_status.user_id),
                    "username": (
                        users_by_id[user_show_status.user_id].username
                        if user_show_status.user_id in users_by_id
                        else None
                    ),
                    "status": user_show_status.status,
                }
                for user_show_status in show.user_show_statuses
            ],
            "user_watch_seasons": [
                {
                    "id": user_watch_season.id,
                    "user_id": cast(int, user_watch_season.user_id),
                    "username": (
                        users_by_id[user_watch_season.user_id].username
                        if user_watch_season.user_id in users_by_id
                        else None
                    ),
                    "season_id": user_watch_season.season_id,
                }
                for user_watch_season in watch_seasons_by_show_id.get(current_show_id, [])
            ],
        }

        for season in show.seasons:
            season_folder_name = cast(str, season.folder_name)
            season_relative_folder_path = (
                os.path.join(show_relative_folder_path, season_folder_name).replace("\\", "/")
                if show_relative_folder_path and season_folder_name
                else None
            )
            season_absolute_folder_path = season.get_full_folder_path()
            season_payload = {
                "id": season.id,
                "title": season.title,
                "description": season.description,
                "image": season.image,
                "number": season.number,
                "folder_name": season_folder_name,
                "folder_path": {
                    "relative": season_relative_folder_path,
                    "absolute": season_absolute_folder_path,
                },
                "episodes": [],
            }

            for episode in season.episodes:
                episode_filename = cast(Optional[str], episode.filename)
                episode_relative_file_path = (
                    os.path.join(season_relative_folder_path, episode_filename).replace("\\", "/")
                    if season_relative_folder_path and episode_filename
                    else None
                )
                episode_absolute_file_path = episode.get_full_file_path()
                season_payload["episodes"].append(
                    {
                        "id": episode.id,
                        "title": episode.title,
                        "description": episode.description,
                        "number": episode.number,
                        "type": episode.type,
                        "filename": episode_filename,
                        "file_path": {
                            "relative": episode_relative_file_path,
                            "absolute": episode_absolute_file_path,
                        },
                        "file_size_bytes": episode.file_size_bytes,
                    }
                )

            show_payload["seasons"].append(season_payload)

        exported_shows.append(show_payload)

    return exported_shows


@router.get("/", response_model=PaginatedResponse)
@authenticated_route
def read_shows(request: Request, db: Session = Depends(get_db)):
    # Get parsed query parameters using the middleware
    parsed_params = get_parsed_query_params(request)

    query = db.query(ShowModel)

    # Use the parsed parameters instead of raw query params
    if "search" in parsed_params and parsed_params["search"]:
        query = ShowModel.filterBySearch(query, parsed_params["search"])

    # Example: Handle userShowStatus filter if it exists
    user: Optional[User] = request.state.user if hasattr(request.state, "user") else None
    if "userShowStatus:in" in parsed_params and user:
        user_show_statuses = parsed_params["userShowStatus:in"]
        query = ShowModel.filterByUserShowStatusIn(query, cast(int, user.id), user_show_statuses)

    if "userShowStatus:notIn" in parsed_params and user:
        user_show_statuses = parsed_params["userShowStatus:notIn"]
        query = ShowModel.filterByUserShowStatusNotIn(query, cast(int, user.id), user_show_statuses)

    # Handle categories filter
    if "categories:anyIn" in parsed_params and parsed_params["categories:anyIn"]:
        query = ShowModel.filterByCategoriesAnyIn(query, parsed_params["categories:anyIn"])

    paginated = paginate_query(query, parsed_params.get("page", 1), parsed_params.get("limit", 10))

    # Serialize ORM objects to Pydantic models
    paginated["data"] = [Show.model_validate(item, from_attributes=True) for item in paginated["data"]]

    return paginated


@router.get("/{show_id}", response_model=Show)
def read_show(show_id: int, db: Session = Depends(get_db)):
    show = db.query(ShowModel).filter(ShowModel.id == show_id).first()
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")
    return show


@router.post("/", response_model=Show)
@authenticated_route
@is_admin
def create_show(request: Request, data: ShowCreate, db: Session = Depends(get_db)):
    db_show = ShowModel(
        description=data.description,
        image=data.image,
    )

    db_show.set_title(data.title)

    db.add(db_show)
    db.flush()

    if data.seasons is not None:
        seasons = [season.model_dump() for season in data.seasons]
        db_show.sync_seasons(seasons, db)

    if data.categories is not None:
        categories = [category.model_dump() for category in data.categories]
        db_show.sync_categories(categories, db)

    db.commit()
    db.refresh(db_show)
    return db_show


@router.put("/{show_id}", response_model=Show)
@authenticated_route
@is_admin
def update_show(request: Request, show_id: int, data: ShowUpdate, db: Session = Depends(get_db)):
    db_show = db.query(ShowModel).filter(ShowModel.id == show_id).first()
    if not db_show:
        raise HTTPException(status_code=404, detail="Show not found")

    update_data = data.model_dump(exclude={"seasons", "title", "categories"})

    for key, value in update_data.items():
        setattr(db_show, key, value)

    # If title is updated, update folder_name (contains the show's episodes)
    if data.title:
        db_show.set_title(data.title)

    if data.seasons is not None:
        seasons = [season.model_dump() for season in data.seasons]
        db_show.sync_seasons(seasons, db)

    if data.categories is not None:
        categories = [category.model_dump() for category in data.categories]
        db_show.sync_categories(categories, db)

    db.commit()
    db.refresh(db_show)
    return db_show


@router.delete("/{show_id}")
@authenticated_route
@is_admin
def delete_show(request: Request, show_id: int, db: Session = Depends(get_db)):
    show = db.query(ShowModel).filter(ShowModel.id == show_id).first()
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")

    show.delete_folder()
    db.delete(show)
    db.commit()
    return {"ok": True}


@router.post("/{show_id}/episodes/{episode_id}/file", response_model=Episode)
@authenticated_route
@is_admin
def upload_episode_file(
    request: Request, show_id: int, episode_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)
):

    episode = db.query(EpisodeModel).filter(EpisodeModel.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    # Attach file to episode model
    episode.attach_file(file)

    episode.update_file_size_bytes()

    db.commit()
    db.refresh(episode)

    return episode


# Removes unused files and folders that may not have been removed due to errors
@router.post("/cleanup")
@authenticated_route
@is_admin
def cleanup_shows(request: Request, db: Session = Depends(get_db)):
    shows = db.query(ShowModel).filter().all()

    files_to_keep: list = []
    for show in shows:
        for season in show.seasons:
            for episode in season.episodes:
                episode_file_path: str = episode.get_full_file_path()
                if not episode_file_path:
                    continue

                if os.path.exists(episode_file_path):
                    files_to_keep.append(episode_file_path)

    base_folder: str | None = Setting.get_shows_folder_path()

    if not base_folder:
        raise HTTPException(status_code=500, detail="Base folder for shows is not configured.")

    removable_file_types: list = ["mkv", "mp4", "mov", "avi", "webm"]

    for root, dirs, files in os.walk(base_folder):
        for file in files:
            file_path = os.path.join(root, file).replace("\\", "/")
            ext = os.path.splitext(file)[1][1:].lower()

            if file_path not in files_to_keep and ext in removable_file_types:
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Failed to remove {file_path}: {e}")

    # Remove empty folders (including those that only contain empty folders)
    for dirpath, dirnames, filenames in os.walk(base_folder, topdown=False):
        try:
            # If all contents are directories and all are empty, remove them recursively
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
        except Exception as e:
            print(f"Failed to remove folder {dirpath}: {e}")

    return {}


@router.post("/{show_id}/episodes/{episode_id}/watch")
def watch_episode(show_id: int, episode_id: int, db: Session = Depends(get_db)):  # Changed parameters
    # Fetch the episode using the ID
    episode = (
        db.query(EpisodeModel).filter(EpisodeModel.id == episode_id, EpisodeModel.season.has(show_id=show_id)).first()
    )

    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found for this show")

    file_path: str | None = episode.get_full_file_path()
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Episode file not found")

    try:
        VLCMediaPlayerUtil.open_file(file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="VLC media player not found on this system.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open file with VLC: {e}")

    return {"ok": True}


@router.post("/{show_id}/seasons/{season_id}/watch")
@optionally_authenticated_route
def watch_season(request: Request, show_id: int, season_id: int, db: Session = Depends(get_db)):
    # Fetch the season using the ID
    season = db.query(SeasonModel).filter(SeasonModel.id == season_id, SeasonModel.show_id == show_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found for this show")

    folder_path: str | None = season.get_full_folder_path()
    if not folder_path or not os.path.isdir(folder_path):
        raise HTTPException(status_code=404, detail="Season folder not found")

    user: Optional[User] = request.state.user if hasattr(request.state, "user") else None

    # Save last watched season in the database and remove old one
    if user:
        db.query(UserWatchSeason).filter(
            UserWatchSeason.user_id == user.id,
            UserWatchSeason.show_id == show_id,
        ).delete()

        new_user_watch_season = UserWatchSeason(season_id=season_id, user_id=user.id, show_id=show_id)
        db.add(new_user_watch_season)
        db.commit()

    try:
        VLCMediaPlayerUtil.open_playlist_from_folder(folder_path)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "VLC media player not found on this system.",
                "exception": str(e),
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to open folder with VLC.",
                "exception": str(e),
            },
        )

    return {"ok": True}
