/*
 * Copyright © 2017 Endless Mobile, Inc.
 *
 * SPDX-License-Identifier: LGPL-2.0+
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with this library. If not, see <https://www.gnu.org/licenses/>.
 *
 * Authors:
 *  - Philip Withnall <withnall@endlessm.com>
 */

#pragma once

#include <gio/gio.h>
#include <glib-object.h>
#include <glib.h>

#include "ostree-repo-finder.h"
#include "ostree-types.h"

G_BEGIN_DECLS

#define OSTREE_TYPE_REPO_FINDER_AVAHI (ostree_repo_finder_avahi_get_type ())

_OSTREE_PUBLIC
G_DECLARE_FINAL_TYPE (OstreeRepoFinderAvahi, ostree_repo_finder_avahi, OSTREE, REPO_FINDER_AVAHI,
                      GObject)

_OSTREE_PUBLIC
OstreeRepoFinderAvahi *ostree_repo_finder_avahi_new (GMainContext *context);

_OSTREE_PUBLIC
void ostree_repo_finder_avahi_start (OstreeRepoFinderAvahi *self, GError **error);

_OSTREE_PUBLIC
void ostree_repo_finder_avahi_stop (OstreeRepoFinderAvahi *self);

G_END_DECLS
