-- engine/markdown/filters/heading_sectionizer.lua
--
-- Lua filter that mirrors the behaviour of the legacy BeautifulSoup based
-- header_sectionizer postprocessor and the add_heading_links postprocessor.
-- It wraps headings in nested <section> elements, ensures deterministic,
-- duplicate-free identifiers, adds data attributes/classes, wraps heading
-- text in a self-link, and appends a copy-link button.

local List = require("pandoc.List")

local button_html = [[<button type="button" class="copy-section-link-button" title="Copy section link to clipboard" tabindex="-1"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512"><path d="M0 256C0 167.6 71.63 96 160 96H256C273.7 96 288 110.3 288 128C288 145.7 273.7 160 256 160H160C106.1 160 64 202.1 64 256C64 309 106.1 352 160 352H256C273.7 352 288 366.3 288 384C288 401.7 273.7 416 256 416H160C71.63 416 0 344.4 0 256zM480 416H384C366.3 416 352 401.7 352 384C352 366.3 366.3 352 384 352H480C533 352 576 309 576 256C576 202.1 533 160 480 160H384C366.3 160 352 145.7 352 128C352 110.3 366.3 96 384 96H480C568.4 96 640 167.6 640 256C640 344.4 568.4 416 480 416zM416 224C433.7 224 448 238.3 448 256C448 273.7 433.7 288 416 288H224C206.3 288 192 273.7 192 256C192 238.3 206.3 224 224 224H416z"></path></svg></button>]]

local function contains(list, value)
  for _, item in ipairs(list) do
    if item == value then
      return true
    end
  end
  return false
end

local function clone_inlines(inlines)
  local copy = List()
  for _, inline in ipairs(inlines) do
    copy:insert(inline)
  end
  return copy
end

local function unique_slug(base, used)
  local slug = base
  if slug == nil or slug == "" then
    slug = "section"
  end

  local count = used[slug]
  if not count then
    used[slug] = 1
    return slug
  end

  count = count + 1
  used[slug] = count
  return string.format("%s-%d", slug, count)
end

local function escape_attr(value)
  -- Basic HTML attribute escaping (slug/data attributes are already safe,
  -- but guard against unexpected characters).
  local escaped = tostring(value)
  escaped = escaped:gsub("&", "&amp;")
  escaped = escaped:gsub("\"", "&quot;")
  escaped = escaped:gsub("<", "&lt;")
  escaped = escaped:gsub(">", "&gt;")
  return escaped
end

local function process_header(header, state)
  local heading_text = pandoc.utils.stringify(header.content)

  local base_slug = header.identifier
  if base_slug == nil or base_slug == "" then
    base_slug = pandoc.utils.slugify(heading_text)
  end

  local slug = unique_slug(base_slug, state.used_slugs)
  header.identifier = slug

  if not contains(header.classes, "heading") then
    header.classes:insert("heading")
  end

  header.attributes["data-level"] = tostring(header.level)
  header.attributes["data-slug"] = slug

  local link_inlines = clone_inlines(header.content)
  local link_title = string.format("Link to section: § '%s'", heading_text)
  local link = pandoc.Link(link_inlines, "#" .. slug, link_title)
  local copy_button = pandoc.RawInline("html", button_html)

  header.content = List({ link, copy_button })

  return header, slug
end

local function section_open_tag(section)
  local parts = {}

  parts[#parts + 1] = string.format('id="%s"', escape_attr(section.id))

  if #section.classes > 0 then
    parts[#parts + 1] = string.format('class="%s"', escape_attr(table.concat(section.classes, " ")))
  end

  for _, attr in ipairs(section.data_attrs_order) do
    local value = section.attributes[attr]
    if value ~= nil then
      parts[#parts + 1] = string.format('%s="%s"', attr, escape_attr(value))
    end
  end

  return string.format("<section %s>", table.concat(parts, " "))
end

local function finalize_section(section)
  local blocks = List()
  blocks:insert(pandoc.RawBlock("html", section_open_tag(section)))

  for _, block in ipairs(section.blocks) do
    blocks:insert(block)
  end

  blocks:insert(pandoc.RawBlock("html", "</section>"))
  return blocks
end

local function append_to_current(stack, block)
  if #stack == 0 then
    return block
  end

  local current = stack[#stack]
  current.blocks:insert(block)
  return nil
end

local function close_section(stack, root)
  local section = table.remove(stack)
  local finalized = finalize_section(section)

  if #stack > 0 then
    local parent = stack[#stack]
    for _, block in ipairs(finalized) do
      parent.blocks:insert(block)
    end
  else
    for _, block in ipairs(finalized) do
      root:insert(block)
    end
  end
end

local function start_new_section(header, slug)
  local level = header.level
  local section_classes = { "block", string.format("level%d", level) }
  local attributes = {
    ["data-level"] = tostring(level),
    ["data-slug"] = slug,
  }

  return {
    level = level,
    id = header.identifier,
    slug = slug,
    classes = section_classes,
    attributes = attributes,
    data_attrs_order = { "data-level", "data-slug" },
    blocks = List({ header }),
  }
end

function Pandoc(doc)
  local state = {
    used_slugs = {},
  }

  local root_blocks = List()
  local stack = {}

  for _, block in ipairs(doc.blocks) do
    if block.t == "Header" then
      local header, slug = process_header(block, state)

      while #stack > 0 and stack[#stack].level >= header.level do
        close_section(stack, root_blocks)
      end

      local section = start_new_section(header, slug)
      stack[#stack + 1] = section
    else
      local appended = append_to_current(stack, block)
      if appended then
        root_blocks:insert(appended)
      end
    end
  end

  while #stack > 0 do
    close_section(stack, root_blocks)
  end

  doc.blocks = root_blocks
  return doc
end
