-- Select the tagged release from Towncrier's parsed RST changelog.
function Pandoc(document)
    local version = os.getenv("RELEASE_VERSION")
    assert(version and version ~= "", "RELEASE_VERSION is required")

    local notes = pandoc.List()
    local selected = false
    local matches = 0
    for _, block in ipairs(document.blocks) do
        if block.t == "Header" and block.level <= 2 then
            selected = block.level == 2
                and pandoc.utils.stringify(block.content):match("^(%S+)") == version
            if selected then
                matches = matches + 1
            end
        elseif selected then
            notes:insert(block)
        end
    end
    assert(matches == 1, "Expected exactly one changelog section for " .. version)
    assert(#notes > 0, "Release notes are empty for " .. version)

    return pandoc.Pandoc(notes):walk({
        Header = function(header)
            header.level = header.level - 1
            return header
        end,
    })
end
