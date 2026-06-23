function buildGroupRoleBadge(group) {
  const role = String(group?.bot_role || "").toLowerCase();
  if (role !== "owner" && role !== "admin") {
    return null;
  }

  const badge = document.createElement("span");
  badge.className = `group-role-badge ${role}`;

  const icon = document.createElement("span");
  icon.className = `group-role-icon ${role}`;
  icon.textContent = role === "owner" ? "主" : "管";
  badge.appendChild(icon);

  const text = document.createElement("span");
  text.textContent = role === "owner" ? "群主" : "管理员";
  badge.appendChild(text);

  return badge;
}

function buildPluginStatusBadge(group) {
  const enabled = Boolean(group?.config?.plugin_enabled);
  const badge = document.createElement("span");
  badge.className = `plugin-status-badge ${enabled ? "enabled" : "disabled"}`;
  if (group?.is_default_group) {
    badge.textContent = enabled ? "默认启用" : "默认关闭";
  } else {
    badge.textContent = enabled ? "已启用" : "未启用";
  }
  return badge;
}

export function renderGroupCards({
  root,
  groups,
  currentGroupId,
  onSelect,
}) {
  root.replaceChildren();

  if (!groups.length) {
    root.classList.add("empty-state");
    root.textContent = "当前没有可显示的群。";
    return;
  }

  root.classList.remove("empty-state");

  groups.forEach((group) => {
    const card = document.createElement("article");
    card.className = "group-card";
    if (group.group_id === currentGroupId) {
      card.classList.add("is-active");
    }

    const avatar = document.createElement("img");
    avatar.className = "group-card-avatar";
    avatar.src =
      group.avatar ||
      "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='96' height='96' viewBox='0 0 96 96'><rect width='96' height='96' rx='16' fill='%23e5e7eb'/><text x='48' y='57' text-anchor='middle' font-size='34' fill='%236b7280' font-family='Arial'>Q</text></svg>";
    avatar.alt = `${group.group_name} 群头像`;
    avatar.loading = "lazy";
    card.appendChild(avatar);

    const main = document.createElement("div");
    main.className = "group-card-main";

    const title = document.createElement("div");
    title.className = "group-card-title";

    const name = document.createElement("div");
    name.className = "group-card-name";
    name.textContent = group.group_name || `群 ${group.group_id}`;
    title.appendChild(name);

    const roleBadge = buildGroupRoleBadge(group);
    if (roleBadge) {
      title.appendChild(roleBadge);
    }
    title.appendChild(buildPluginStatusBadge(group));

    main.appendChild(title);

    const subline = document.createElement("div");
    subline.className = "group-card-subline";
    const idText = document.createElement("span");
    idText.className = "group-card-id";
    const metaText = document.createElement("span");
    if (group.is_default_group) {
      idText.textContent = "默认模板";
      metaText.textContent = "新群继承这里的配置";
    } else {
      idText.textContent = String(group.group_id);
      metaText.textContent = `${group.member_count || 0} 人`;
    }
    subline.append(idText, metaText);
    main.appendChild(subline);

    card.appendChild(main);

    card.addEventListener("click", () => {
      onSelect?.(group.group_id);
    });

    root.appendChild(card);
  });
}

export function renderGroupDetailHeader(els, payload) {
  const info = payload.group_info || {};
  els.currentGroupName.textContent = info.group_name || `群 ${payload.group_id}`;
}
