"""Prompt templates for semantic audit review tasks."""

from __future__ import annotations


ATTACHMENT_REVIEW_PROMPT = (
    "你是运维工单附件复核员。请判断附件是否真的是报告、证书、曲线图或现场照片，"
    "并核对附件内容是否足以支持工单结论。输出结论、证据摘要和置信度。"
)

REMARK_REVIEW_PROMPT = (
    "你是运维工单语义复核员。请判断备注是否覆盖原因、措施、结果，"
    "并说明是否足以支持工单闭环结论。输出结论、证据摘要和置信度。"
)

REMARK_SEMANTIC_JSON_PROMPT = (
    "请判断下列运维工单备注是否完整说明原因、措施、结果。"
    "problem_description 必须具体描述备注存在或不存在的问题，不要输出固定整改建议。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"is_complete\":bool,\"has_cause\":bool,\"has_action\":bool,\"has_result\":bool,"
    "\"problem_description\":string,\"confidence\":number}"
)

REMARK_BATCH_SEMANTIC_JSON_PROMPT = (
    "请批量判断运维工单备注是否完整说明原因、措施、结果。"
    "仅对故障、异常、报警、待定、处置闭环类场景使用该标准；不要把计划任务主表描述充分性混入本任务。"
    "problem_description 必须具体描述每个工单备注的问题，不要输出固定整改建议。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"results\":[{\"working_order_code\":string,\"is_complete\":bool,\"has_cause\":bool,"
    "\"has_action\":bool,\"has_result\":bool,\"problem_description\":string,\"confidence\":number}]}"
)

ORDER_DESCRIPTION_SEMANTIC_JSON_PROMPT = (
    "请判断运维工单主表标题和内容是否足以说明本次工单的作业对象、作业类型或任务目的。"
    "不要套用故障闭环的原因、措施、结果三要素；周检、巡检、计划任务可由RF表、工单类型/周期、流程记录补充上下文。"
    "如果只有'计划任务单'且无任何RF表、作业类型、设备/站点/任务上下文，应判为不充分；"
    "如果虽然主表内容泛化，但工单类型/周期和RF表已经清楚表明是例行检查任务，可判为充分或不作为最终问题。"
    "problem_description 必须说明主表描述是否存在具体问题，不要输出固定整改建议。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"is_sufficient\":bool,\"has_task_object\":bool,\"has_task_type\":bool,"
    "\"reason\":string,\"problem_description\":string,\"confidence\":number}"
)

ATTACHMENT_QUALITY_JSON_PROMPT = (
    "请根据识别文本判断附件是否完整。"
    "证书重点检查是否只是封面或首页，报告重点检查目录是否更新。"
    "problem_description 必须具体描述附件内容问题，不要输出固定整改建议。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"is_complete\":bool,\"issues\":[string],\"problem_description\":string,\"confidence\":number}"
)

PHOTO_WATERMARK_JSON_PROMPT = (
    "请判断照片OCR文本中是否包含水印及日期。仅输出JSON，不要输出解释。格式为："
    "{\"has_watermark\":bool,\"has_date\":bool,\"date_text\":string,\"problem_description\":string,\"confidence\":number}"
)

VALUE_CONSISTENCY_JSON_PROMPT = (
    "请判断附件中的读数与表单值是否一致。仅输出JSON，不要输出解释。格式为："
    "{\"is_consistent\":bool,\"attachment_value\":string,\"form_value\":string,\"difference\":number,"
    "\"problem_description\":string,\"confidence\":number}"
)

FILENAME_SEMANTIC_JSON_PROMPT = (
    "请仅根据附件文件名语义，判断这些文件名是否覆盖指定的运维证据类型。"
    "不要推断图片内容，不要做OCR，不要因为扩展名是图片就认为覆盖具体证据类型。"
    "可根据中文业务含义、同义表达、缩写和上下文归类。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"covered_types\":{string:[string]},\"missing_types\":[string],"
    "\"uncertain_types\":[string],\"evidence\":[{\"type\":string,\"filenames\":[string],\"reason\":string}],"
    "\"confidence\":number}"
)

FILENAME_BATCH_SEMANTIC_JSON_PROMPT = (
    "请批量根据附件文件名语义，判断每个工单的附件是否覆盖指定的站点设备维护现场照片证据类型。"
    "每个工单会提供required_types和type_definitions，请按type_definitions理解英文类型编码。"
    "不要推断图片内容，不要做OCR，不要因为扩展名是图片就认为覆盖具体证据类型。"
    "可根据中文业务含义、同义表达、缩写和上下文归类。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"results\":[{\"working_order_code\":string,\"covered_types\":{string:[string]},"
    "\"missing_types\":[string],\"uncertain_types\":[string],"
    "\"evidence\":[{\"type\":string,\"filenames\":[string],\"reason\":string}],\"confidence\":number}]}"
)

NO_DEVICE_EXPLANATION_JSON_PROMPT = (
    "请判断设备型号字段为空、/、无等占位值时，运行情况文本是否已经明确说明该站点没有对应设备、"
    "设备未配置、合同不包含、设备停用或不适用。"
    "只做语义等价判断，不要依赖固定关键词；如果只是'无'、'/'、'正常'等低信息内容，应判为说明不足。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"is_explained\":bool,\"reason\":string,\"confidence\":number}"
)

NO_DEVICE_BATCH_JSON_PROMPT = (
    "请批量判断 RF_W_OTHERDEVICECHECK 中设备型号为占位值时，运行情况是否已经明确说明该站点没有对应设备、"
    "设备未配置、合同不包含、设备停用或不适用。"
    "同一类问题使用同一标准：只做语义等价判断，不依赖固定关键词；如果只是'无'、'/'、'正常'等低信息内容，应判为说明不足。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"results\":[{\"item_id\":string,\"is_explained\":bool,\"reason\":string,\"confidence\":number}]}"
)

PM_TAPE_USAGE_BATCH_JSON_PROMPT = (
    "请批量判断颗粒物周检 RF_W_PMCHECK 中耗材使用/处置字段填写是否规范。"
    "每个item会给出 pollutant_type、device_model、instrument_type、field_label 和 field_value。"
    "如果 instrument_type=paper_tape，应判断纸带使用量及处置情况是否充分：明确说明纸带足够一周或足够使用、"
    "填写了可判断足量的剩余时间/比例/数量，或说明已更换新的纸带，可判为规范。"
    "如果 instrument_type=teom_filter，说明DEVICEMODEL包含1405，为TEOM/振荡天平类无纸带设备，"
    "应判断TEOM滤膜负载及处置情况是否充分：应说明滤膜负载情况或已更换滤膜；"
    "如果负载达到或超过80%，且没有说明已更换或已处置，应判为不规范。"
    "如果为空、/、仅写正常/无/已检查等低信息内容，或无法判断对应耗材状态，应判为不规范。"
    "只做语义判断，不依赖固定关键词。"
    "problem_description 必须具体说明字段内容为什么充分或不充分，不要输出固定整改建议。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"results\":[{\"item_id\":string,\"is_valid\":bool,\"reason\":string,\"problem_description\":string}]}"
)

ORDER_DESCRIPTION_BATCH_JSON_PROMPT = (
    "请批量判断运维工单主表标题和内容是否足以说明本次工单的作业对象、作业类型或任务目的。"
    "不要套用故障闭环的原因、措施、结果三要素；周检、巡检、计划任务可由RF表、工单类型/周期、流程记录补充上下文。"
    "如果只有'计划任务单'且无任何RF表、作业类型、设备/站点/任务上下文，应判为不充分；"
    "如果虽然主表内容泛化，但工单类型/周期和RF表已经清楚表明是例行检查任务，可判为充分或不作为最终问题。"
    "problem_description 必须说明主表描述是否存在具体问题，不要输出固定整改建议。"
    "仅输出JSON，不要输出解释。格式为："
    "{\"results\":[{\"working_order_code\":string,\"is_sufficient\":bool,\"has_task_object\":bool,"
    "\"has_task_type\":bool,\"reason\":string,\"problem_description\":string,\"confidence\":number}]}"
)
