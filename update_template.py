import re

# 读取原始模板
with open('app/templates/admin/project.html', 'r', encoding='utf-8') as file:
    content = file.read()

# 修改页面头部，添加编辑项目按钮
pattern = r'<div>\s+<a href="\{\{ url_for\(\'admin\.view_selections\', project_id=project\.id\) \}\}" class="btn">View Selections</a>'
replacement = r'<div>\n        <a href="{{ url_for(\'admin.edit_project\', project_id=project.id) }}" class="btn btn-primary">Edit Project</a>\n        <a href="{{ url_for(\'admin.view_selections\', project_id=project.id) }}" class="btn">View Selections</a>'

modified_content = re.sub(pattern, replacement, content)

# 保存修改后的模板
with open('app/templates/admin/project.html', 'w', encoding='utf-8') as file:
    file.write(modified_content)

print("Template updated successfully!") 