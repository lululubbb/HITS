package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

public class CSVRecord_1_5Test {

    @Test
    @Timeout(8000)
    public void testCSVRecordConstructorAndFields() throws Exception {
        String[] values = new String[]{"a", "b", "c"};
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("col1", 0);
        mapping.put("col2", 1);
        String comment = "comment";
        long recordNumber = 123L;

        // Use reflection to get constructor (package-private)
        Constructor<CSVRecord> ctor = CSVRecord.class.getDeclaredConstructor(
                String[].class, Map.class, String.class, long.class);
        ctor.setAccessible(true);

        CSVRecord record = ctor.newInstance(values, mapping, comment, recordNumber);

        // Access private fields via reflection to verify initialization
        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);
        String[] storedValues = (String[]) valuesField.get(record);
        assertArrayEquals(values, storedValues);

        Field mappingField = CSVRecord.class.getDeclaredField("mapping");
        mappingField.setAccessible(true);
        Map<?, ?> storedMapping = (Map<?, ?>) mappingField.get(record);
        assertEquals(mapping, storedMapping);

        Field commentField = CSVRecord.class.getDeclaredField("comment");
        commentField.setAccessible(true);
        String storedComment = (String) commentField.get(record);
        assertEquals(comment, storedComment);

        Field recordNumberField = CSVRecord.class.getDeclaredField("recordNumber");
        recordNumberField.setAccessible(true);
        long storedRecordNumber = recordNumberField.getLong(record);
        assertEquals(recordNumber, storedRecordNumber);
    }

    @Test
    @Timeout(8000)
    public void testCSVRecordConstructorWithNullValues() throws Exception {
        Map<String, Integer> mapping = Collections.emptyMap();
        String comment = null;
        long recordNumber = 0L;

        Constructor<CSVRecord> ctor = CSVRecord.class.getDeclaredConstructor(
                String[].class, Map.class, String.class, long.class);
        ctor.setAccessible(true);

        // Pass null explicitly for String[] values parameter
        CSVRecord record = ctor.newInstance((Object) null, mapping, comment, recordNumber);

        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);
        String[] storedValues = (String[]) valuesField.get(record);
        // Should be EMPTY_STRING_ARRAY, which is a zero-length array
        assertNotNull(storedValues);
        assertEquals(0, storedValues.length);
    }
}