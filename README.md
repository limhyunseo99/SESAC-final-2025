# SeSAC_2025_FinalProject

## SeSAC 파이널 프로젝트에서 사용 중인 Asset 파일을 관리하는 저장소입니다.

```
⚠ 반드시 작업 전 모든 애셋을 업데이트해주세요.
```

# [파일·폴더 네이밍 규칙]
파일을 저장할 때에는 아래의 규칙에 따라 파일명을 작성해주세요.

■ 공통
- 소문자 + snake_case 사용
- 영문/숫자만, 공백은 "_"로
- 버전은 v1, v1.1 형식
- prefix 사용: raw_, clean_, final_, draft_

■ 코드 파일
- 기능_설명.py  (예: data_preprocessing.py)
- 테스트: test_파일명.py

■ 데이터 파일
- RAW:    raw_내용_날짜.csv
- CLEAN:  clean_내용_v1.csv
- PROC:   processed_내용.pkl
- 분할:   train_dataset_v1.csv 등

■ 문서 파일
- meeting_notes_YYYYMMDD.md
- report_v1.pdf / diagram_v1.png

■ 권장 폴더 구조
src/, data/raw-clean-processed/, docs/, notebooks/







# [Github Desktop 사용법]

## Step 1. Clone repository(원격 저장소 다운로드)
공유 받은 리포지토리(원격 저장소, 이하 리포)를 자신의 하드(내부 저장소)에 저장하는 과정입니다. 이 과정을 거쳐야 여러분의 PC에서 Github의 원격 저장소에 저장된 파일에 접근하고, 다운로드/업로드를 자유롭게 사용할 수 있습니다. 위에 첨부된 사진의 번호를 따라 아래 설명대로 진행하시면 됩니다.

1. 좌측 상단의 Current repository - Add - Clone repository를 누른다.
2. Clone을 수행할 리포를 선택한다.
3. Local path를 원하는 폴더로 지정한다.(앞으로 이 폴더 안에서 일어나는 모든 변경 사항은 깃에 반영됩니다.) 이후 하단 Clone 파란 버튼을 누른다.
    - Assets 리포 Path는 반드시 Ludico_KNOCKturne 리포를 먼저 Clone한 후에 해당 리포가 Clone된 경로 하위 Content 폴더로 지정하셔야 합니다.
      > ex. 저는 [D:\GitHub]에 Ludico_KNOCKturne을 Clone했고, [D:\GitHub\Ludico_KNOCKturne\Content]에 Assets 리포를 Clone했습니다.
5. Clone한 리포가 깃허브 데스크탑 내에 잘 위치했는지 확인한다.

<br><br>

## Step 2. Commit changes(애셋 변경 사항 업로드)

- 리포 내에 특정 애셋 파일을 변경(추가, 삭제 포함)했다면 좌측 `Changes` 탭에 변경 내용이 반영되었을 겁니다. 기존에 Asset update list에 작성하던 것처럼 Summary를 작성하고 부가 설명이 필요한 경우 Description을 작성합니다.

<br><br>

## Step 3. Github Desktop Layout(깃허브 데스크탑 레이아웃 설명)
앞서 사용한 기본 Github Desktop 레이아웃을 설명하는 내용입니다.



### [기본 용어 설명]
- `리포지토리(저장소)` : 공유 중인 프로젝트 내용이 저장된 공간
- `체인지` : 내 로컬 저장소 내에서의 변경 사항(리포는 아직 아무것도 바뀌지 않음)
- `커밋` : 원격 저장소에 로컬 저장소의 변경 사항을 기록(여기서 리포가 실제로 변경됨)
- `푸시` : 커밋한 내용을 다른 사람이 참조할 수 있도록 공유
- `풀` : 다른 사람이 푸시한 내용을 나의 로컬 저장소로 가져옴.

1. ***Current repository***<br>
  현재 선택 중인 리포를 의미합니다. 특정 리포에 Push/Pull을 하기 위해선 Current repository를 반드시 설정해주어야 합니다.

2. ***Current branch***<br>
  현재 선택 중인 브랜치입니다. 브랜치는 개인의 작업 공간이라고 생각하면 됩니다. 잠시 설명이 있겠습니다.<br>
  리포는 여러 사람이 공유하는 저장소이고, 어떤 파일이든 누구나 접근할 수 있습니다. 이때, 두 명의 사람이 A.txt라는 파일을 동시에 수정하고 커밋, 푸시했을 때 변경 사항이 올바르게 입력되지 않을 수 있습니다. 이를 적절하게 처리해주는 과정을 합병(Merge)라 합니다. 실제로 반영할 사항과 버릴 사항을 결정하는 작업입니다.<br>
  이것을 위해 일단 자신의 브랜치에서 작업을 하고 커밋한 후, 작업이 완료 되었을 때 각자의 브랜치 변경 사항을 master에 병합하여 충돌을 방지합니다. 어떤 브랜치에 작업 사항을 적용할 것인지 여기서 결정할 수 있습니다.

3. ***Changes list***<br>
  Change의 목록을 보여줍니다. 보통 파일 단위로 볼 수 있으며, 각 Change를 클릭하면 세부 내용을 확인할 수 있습니다. 필요한 경우 리스트에서 Discard하여 필요한 Change만 커밋할 수 있습니다.

4. ***Commit Summary***<br>
  Changes를 커밋할 땐 반드시 간단한 설명을 달아야 합니다. 개인적으로 이 Summary에 예민해서 반드시 무슨 변경에 대한 내용인지 명확하게 적어 주셨으면 합니다. 간혹 asd, zzz 식으로 다는 사람 있는데 전 그런 거 많이 싫어합니다.. 양해좀.. 밑에 Description은 필요하시면 다는데 안 다셔도 무방합니다.

5. ***Commit to \~***<br>
  Current branch에 Changes를 적용합니다. 반드시 커밋을 해야 푸시로 공유할 수 있습니다.

6. ***Fetch origin***<br>
  이 항목은 경우에 따라 Fetch/Push/Pull로 나뉩니다.
    - Fetch : 리포의 변경 사항이 있는지 체크합니다.
    - Push : 나의 커밋을 원격 저장소에 공유합니다.
    - Pull : 다른 사람이 원격 저장소에 저장한 정보를 나의 로컬 저장소로 가져옴.












