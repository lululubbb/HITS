package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CSVRecord_8_5Test {

    private CSVRecord csvRecord;
    private String[] values;
    private Map<String, Integer> mapping;
    private String comment;
    private long recordNumber;

    @BeforeEach
    void setUp() throws Exception {
        values = new String[] {"value1", "value2", "value3"};
        mapping = new HashMap<>();
        mapping.put("col1", 0);
        mapping.put("col2", 1);
        comment = "This is a comment";
        recordNumber = 42L;
        csvRecord = createCSVRecord(values, mapping, comment, recordNumber);
    }

    private CSVRecord createCSVRecord(String[] values, Map<String, Integer> mapping, String comment, long recordNumber) throws Exception {
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        return constructor.newInstance(values, mapping, comment, recordNumber);
    }

    @Test
    @Timeout(8000)
    void testValuesMethod() throws Exception {
        // Use reflection to invoke the package-private values() method
        var method = CSVRecord.class.getDeclaredMethod("values");
        method.setAccessible(true);

        String[] result = (String[]) method.invoke(csvRecord);

        assertNotNull(result);
        assertArrayEquals(values, result);
    }

    @Test
    @Timeout(8000)
    void testValuesMethodWithEmptyValues() throws Exception {
        CSVRecord emptyRecord = createCSVRecord(new String[0], Collections.emptyMap(), null, 0L);

        var method = CSVRecord.class.getDeclaredMethod("values");
        method.setAccessible(true);

        String[] result = (String[]) method.invoke(emptyRecord);

        assertNotNull(result);
        assertEquals(0, result.length);
    }
}