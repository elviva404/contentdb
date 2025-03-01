# ContentDB
# Copyright (C) 2018-21  rubenwardy
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

import datetime
from typing import Tuple, List

from flask import url_for

from . import db
from .users import Permission, UserRank
from .packages import Package

watchers = db.Table("watchers",
	db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
	db.Column("thread_id", db.Integer, db.ForeignKey("thread.id"), primary_key=True)
)


class Thread(db.Model):
	id         = db.Column(db.Integer, primary_key=True)

	package_id = db.Column(db.Integer, db.ForeignKey("package.id"), nullable=True)
	package    = db.relationship("Package", foreign_keys=[package_id], back_populates="threads")

	is_review_thread = db.relationship("Package", foreign_keys=[Package.review_thread_id], back_populates="review_thread")

	review_id  = db.Column(db.Integer, db.ForeignKey("package_review.id"), nullable=True)
	review     = db.relationship("PackageReview", foreign_keys=[review_id], cascade="all, delete")

	author_id  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	author     = db.relationship("User", back_populates="threads", foreign_keys=[author_id])

	title      = db.Column(db.String(100), nullable=False)
	private    = db.Column(db.Boolean, server_default="0", nullable=False)

	locked     = db.Column(db.Boolean, server_default="0", nullable=False)

	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	replies    = db.relationship("ThreadReply", back_populates="thread", lazy="dynamic",
			order_by=db.asc("thread_reply_id"), cascade="all, delete, delete-orphan")

	watchers   = db.relationship("User", secondary=watchers, backref="watching")

	def get_description(self):
		comment = self.replies[0].comment.replace("\r\n", " ").replace("\n", " ").replace("  ", " ")
		if len(comment) > 100:
			return comment[:97] + "..."
		else:
			return comment

	def getViewURL(self, absolute=False):
		if absolute:
			from ..utils import abs_url_for
			return abs_url_for("threads.view", id=self.id)
		else:
			return url_for("threads.view", id=self.id, _external=False)

	def getSubscribeURL(self):
		return url_for("threads.subscribe", id=self.id)

	def getUnsubscribeURL(self):
		return url_for("threads.unsubscribe", id=self.id)

	def checkPerm(self, user, perm):
		if not user.is_authenticated:
			return perm == Permission.SEE_THREAD and not self.private

		if type(perm) == str:
			perm = Permission[perm]
		elif type(perm) != Permission:
			raise Exception("Unknown permission given to Thread.checkPerm()")

		isMaintainer = user == self.author or (self.package is not None and self.package.author == user)
		if self.package:
			isMaintainer = isMaintainer or user in self.package.maintainers

		canSee = not self.private or isMaintainer or user.rank.atLeast(UserRank.APPROVER)

		if perm == Permission.SEE_THREAD:
			return canSee

		elif perm == Permission.COMMENT_THREAD:
			return canSee and (not self.locked or user.rank.atLeast(UserRank.MODERATOR))

		elif perm == Permission.LOCK_THREAD:
			return user.rank.atLeast(UserRank.MODERATOR)

		elif perm == Permission.DELETE_THREAD:
			from app.utils.models import get_system_user
			return (self.author == get_system_user() and self.package and
					user in self.package.maintainers) or user.rank.atLeast(UserRank.MODERATOR)

		else:
			raise Exception("Permission {} is not related to threads".format(perm.name))

	def get_latest_reply(self):
		return ThreadReply.query.filter_by(thread_id=self.id).order_by(db.desc(ThreadReply.id)).first()


class ThreadReply(db.Model):
	id         = db.Column(db.Integer, primary_key=True)

	thread_id  = db.Column(db.Integer, db.ForeignKey("thread.id"), nullable=False)
	thread = db.relationship("Thread", back_populates="replies", foreign_keys=[thread_id])

	comment    = db.Column(db.String(2000), nullable=False)

	author_id  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	author     = db.relationship("User", back_populates="replies", foreign_keys=[author_id])

	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	def get_url(self):
		return url_for('threads.view', id=self.thread.id) + "#reply-" + str(self.id)

	def checkPerm(self, user, perm):
		if not user.is_authenticated:
			return False

		if type(perm) == str:
			perm = Permission[perm]
		elif type(perm) != Permission:
			raise Exception("Unknown permission given to ThreadReply.checkPerm()")

		if perm == Permission.EDIT_REPLY:
			return user.rank.atLeast(UserRank.MEMBER if user == self.author else UserRank.MODERATOR) and not self.thread.locked

		elif perm == Permission.DELETE_REPLY:
			return user.rank.atLeast(UserRank.MODERATOR) and self.thread.replies[0] != self

		else:
			raise Exception("Permission {} is not related to threads".format(perm.name))


class PackageReview(db.Model):
	id         = db.Column(db.Integer, primary_key=True)

	package_id = db.Column(db.Integer, db.ForeignKey("package.id"), nullable=True)
	package    = db.relationship("Package", foreign_keys=[package_id], back_populates="reviews")

	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

	author_id  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
	author     = db.relationship("User", foreign_keys=[author_id], back_populates="reviews")

	recommends = db.Column(db.Boolean, nullable=False)

	thread     = db.relationship("Thread", uselist=False, back_populates="review")
	votes      = db.relationship("PackageReviewVote", back_populates="review", cascade="all, delete, delete-orphan")

	score      = db.Column(db.Integer, nullable=False, default=1)

	def get_totals(self, current_user = None) -> Tuple[int,int,bool]:
		votes: List[PackageReviewVote] = self.votes
		pos = sum([ 1 for vote in votes if vote.is_positive ])
		neg = sum([ 1 for vote in votes if not vote.is_positive])
		user_vote = next(filter(lambda vote: vote.user == current_user, votes), None)
		return pos, neg, user_vote.is_positive if user_vote else None

	def getAsDictionary(self, include_package=False):
		pos, neg, _user = self.get_totals()
		ret = {
			"is_positive": self.recommends,
			"user": {
				"username": self.author.username,
				"display_name": self.author.display_name,
			},
			"created_at": self.created_at.isoformat(),
			"votes": {
				"helpful": pos,
				"unhelpful": neg,
			},
			"title": self.thread.title,
			"comment": self.thread.replies[0].comment,
		}
		if include_package:
			ret["package"] = self.package.getAsDictionaryKey()
		return ret

	def asSign(self):
		return 1 if self.recommends else -1

	def getEditURL(self):
		return self.package.getURL("packages.review")

	def getDeleteURL(self):
		return url_for("packages.delete_review",
				author=self.package.author.username,
				name=self.package.name)

	def getVoteUrl(self, next_url=None):
		return url_for("packages.review_vote",
				author=self.package.author.username,
				name=self.package.name,
				review_id=self.id,
				r=next_url)

	def update_score(self):
		(pos, neg, _) = self.get_totals()
		self.score = 3 * (pos - neg) + 1


class PackageReviewVote(db.Model):
	review_id = db.Column(db.Integer, db.ForeignKey("package_review.id"), primary_key=True)
	review = db.relationship("PackageReview", foreign_keys=[review_id], back_populates="votes")
	user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
	user = db.relationship("User", foreign_keys=[user_id], back_populates="review_votes")

	is_positive = db.Column(db.Boolean, nullable=False)

	created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
