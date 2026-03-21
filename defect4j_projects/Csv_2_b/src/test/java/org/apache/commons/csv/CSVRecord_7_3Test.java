package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.lang.reflect.Constructor;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class CSVRecord_7_3Test {

    private CSVRecord csvRecord;
    private String[] values;
    private Map<String, Integer> mapping;
    private String comment;
    private long recordNumber;

    @BeforeEach
    public void setUp() throws Exception {
        values = new String[] { "a", "b", "c" };
        mapping = mock(Map.class);
        comment = "comment";
        recordNumber = 123L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        csvRecord = constructor.newInstance((Object) values, mapping, comment, recordNumber);
    }

    @Test
    @Timeout(8000)
    public void testIterator_returnsIteratorOverValues() {
        Iterator<String> iterator = csvRecord.iterator();
        assertNotNull(iterator);

        // Collect all elements from iterator and compare with original values
        String[] iteratedValues = toArray(iterator);
        assertArrayEquals(values, iteratedValues);
    }

    private String[] toArray(Iterator<String> iterator) {
        List<String> list = new ArrayList<>();
        while (iterator.hasNext()) {
            list.add(iterator.next());
        }
        return list.toArray(new String[0]);
    }
}