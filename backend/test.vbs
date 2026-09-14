' VBS 测试脚本：测试 Word 替换功能
' 保存为 test.vbs 并运行：cscript test.vbs

Option Explicit

Dim objWord, objDoc
Dim strFile, strFind, strReplace
Dim objFind
Dim bResult

strFile = "D:\溯源\报告模板\2025年11月3日臭氧垂直.docx"
strFind = "数据特征分析："
strReplace = "数据特征分析：【VBS测试替换成功】2025年11月3日"

' 创建 Word 应用
Set objWord = CreateObject("Word.Application")
objWord.Visible = False
objWord.DisplayAlerts = False

' 打开文档
Set objDoc = objWord.Documents.Open(strFile)

WScript.Echo "文档已打开"
WScript.Echo "查找文本: " & strFind
WScript.Echo "替换文本: " & strReplace

' 执行替换
Set objFind = objDoc.Content.Find
objFind.ClearFormatting

bResult = objFind.Execute( _
    FindText:=strFind, _
    ReplaceWith:=strReplace, _
    MatchCase:=False, _
    MatchWholeWord:=False, _
    Forward:=True, _
    Wrap:=1, _
    Replace:=2 _
)

WScript.Echo "替换结果: " & bResult

' 保存并关闭
objDoc.Save
objDoc.Close
objWord.Quit

WScript.Echo "完成！"

Set objDoc = Nothing
Set objWord = Nothing
