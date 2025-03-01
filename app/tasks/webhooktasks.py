# ContentDB
# Copyright (C) 2021 rubenwardy
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from typing import Optional

import requests

from app import app
from app.models import User
from app.tasks import celery

@celery.task()
def post_discord_webhook(username: Optional[str], content: str, is_queue: bool):
	discord_url = app.config.get("DISCORD_WEBHOOK_QUEUE" if is_queue else "DISCORD_WEBHOOK_FEED")
	if discord_url is None:
		return

	json = {
		"content": content,
	}

	if username:
		json["username"] = username
		user = User.query.filter_by(username=username).first()
		if user:
			json["avatar_url"] = user.getProfilePicURL().replace("/./", "/")

	requests.post(discord_url, json=json)
